import os
import re
import chardet
import unidiff
import shutil
import argparse
import datasets
import traceback
import subprocess
from git import Repo
from tqdm import tqdm
from pathlib import Path
from tempfile import TemporaryDirectory
from utils import save_tsv_dict, save_file_jsonl
from get_repo_structure.get_repo_structure import get_project_structure_from_scratch
from get_repo_structure.get_patch_info import *

# %% Get oracle file contents

# get oracle file contents from the repo
class ContextManager:
    def __init__(self, repo_path, base_commit, verbose=False):
        self.repo_path = Path(repo_path).resolve().as_posix()
        self.old_dir = os.getcwd()
        self.base_commit = base_commit
        self.verbose = verbose

    def __enter__(self):
        os.chdir(self.repo_path)
        cmd = f"git reset --hard {self.base_commit} && git clean -fdxq"
        if self.verbose:
            subprocess.run(cmd, shell=True, check=True)
        else:
            subprocess.run(
                cmd,
                shell=True,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return self

    def get_environment(self):
        raise NotImplementedError()  # TODO: activate conda environment and return the environment file

    def get_readme_files(self):
        files = os.listdir(self.repo_path)
        files = list(filter(lambda x: os.path.isfile(x), files))
        files = list(filter(lambda x: x.lower().startswith("readme"), files))
        return files

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.chdir(self.old_dir)


class AutoContextManager(ContextManager):
    """Automatically clones the repo if it doesn't exist"""

    def __init__(self, instance, root_dir=None, verbose=False, token=None):
        if token is None:
            token = os.environ.get("GITHUB_TOKEN", "git")
        self.tempdir = None
        if root_dir is None:
            self.tempdir = TemporaryDirectory()
            root_dir = self.tempdir.name
        self.root_dir = root_dir
        repo_dir = os.path.join(self.root_dir, instance["repo"].replace("/", "__"))
        if not os.path.exists(repo_dir):
            repo_url = (
                f"https://{token}@github.com/swe-bench/"
                + instance["repo"].replace("/", "__")
                + ".git"
            )
            if verbose:
                print(f"Cloning {instance['repo']} to {root_dir}")
            Repo.clone_from(repo_url, repo_dir)
        super().__init__(repo_dir, instance["base_commit"], verbose=verbose)
        self.instance = instance

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.tempdir is not None:
            self.tempdir.cleanup()
        return super().__exit__(exc_type, exc_val, exc_tb)


def ingest_files(filenames):
    files_dict = dict()
    for filename in filenames:
        with open(filename) as f:
            content = f.read()
        files_dict[filename] = content
    return files_dict

def get_oracle_filenames(instance):
    """
    Returns the filenames that are changed in the patch
    """
    source_files = {
        patch_file.source_file.split("a/", 1)[-1]
        for patch_file in unidiff.PatchSet(instance["patch"])
    }
    gold_docs = set()
    for source_file in source_files:
        gold_docs.add(source_file)
    return gold_docs


# get all file contents from the repo
def is_test(name, test_phrases=None):
    if test_phrases is None:
        test_phrases = ["test", "tests", "testing"]
    words = set(re.split(r" |_|\/|\.", name.lower()))
    return any(word in words for word in test_phrases)

def list_files(root_dir, include_tests=False):
    files = []
    for filename in Path(root_dir).rglob("*.py"):
        if not include_tests and is_test(filename.as_posix()):
            continue
        files.append(filename.relative_to(root_dir).as_posix())
    return files

def detect_encoding(filename):
    """
    Detect the encoding of a file
    """
    with open(filename, "rb") as file:
        rawdata = file.read()
    return chardet.detect(rawdata)["encoding"]

def ingest_directory_contents(root_dir, include_tests=False):
    files_content = {}
    for relative_path in list_files(root_dir, include_tests=include_tests):
        filename = os.path.join(root_dir, relative_path)
        encoding = detect_encoding(filename)
        if encoding is None:
            content = "[BINARY DATA FILE]"
        else:
            try:
                with open(filename, encoding=encoding) as file:
                    content = file.read()
            except (UnicodeDecodeError, LookupError):
                content = "[BINARY DATA FILE]"
        files_content[relative_path] = content
    return files_content

def get_file_contents(input_instances, verbose: bool = False, tmp_dir: str = "/scratch"):
    orig_dir = os.getcwd()
    with TemporaryDirectory(dir=tmp_dir if os.path.exists(tmp_dir) else "/tmp") as root_dir:
        for instance_id, instance in tqdm(
            input_instances.items(),
            total=len(input_instances),
            desc="Getting file contents",
        ):
            try:
                with AutoContextManager(instance, root_dir, verbose=verbose) as cm:
                    readmes = cm.get_readme_files()
                    instance["readmes"] = ingest_files(readmes)
                    instance["oracle_file_contents"] = ingest_files(get_oracle_filenames(instance))
                    instance["file_contents"] = ingest_directory_contents(cm.repo_path)
                    assert all([
                        okey in instance["file_contents"] 
                        for okey in instance["oracle_file_contents"].keys()
                    ])
            except Exception as e:
                print(f"Failed on instance {instance_id}", e)
                traceback.print_exc()
            finally:
                # if AutoContextManager fails to exit properly future exits will return the wrong directory
                os.chdir(orig_dir)
    os.chdir(orig_dir)

def file(dataset, name):
    for item in dataset:
        queries = [{
            "_id": item["instance_id"],
            "text": item["problem_statement"], 
            "metadata": {}
        }]
        item_dict = {item["instance_id"]: item}
        get_file_contents(item_dict, tmp_dir=args.tmp_dir)
        docs = []
        for instance_id, instance in item_dict.items():
            print(f"Instance #{instance_id}: {len(instance['oracle_file_contents'])} oracle / {len(instance['file_contents'])} files")
            for filename, content in instance["file_contents"].items():
                docs.append({
                    "_id": f"{instance_id}_{filename}",
                    "title": filename,
                    "text": content,
                    "metadata": {},
                })

        qrels = []
        for instance_id, instance in item_dict.items():
            for filename, content in instance["oracle_file_contents"].items():
                qrels.append({
                    "query-id": instance_id,
                    "corpus-id": f"{instance_id}_{filename}",
                    "score": 1
                }) 

        path = os.path.join(args.dataset_dir, f"{name}_{instance_id}")
        os.makedirs(path, exist_ok=True)
        os.makedirs(os.path.join(path, "qrels"), exist_ok=True)
        
        save_file_jsonl(queries, os.path.join(path, "queries.jsonl"))
        save_file_jsonl(docs, os.path.join(path, "corpus.jsonl"))
        qrels_path = os.path.join(path, "qrels", "test.tsv")
        save_tsv_dict(qrels, qrels_path, ["query-id", "corpus-id", "score"])

def function(dataset, name):
    #TODO: validate this extensively on each instance
    for i, item in tqdm(enumerate(dataset), total = len(dataset), colour= 'blue'):
        if os.path.exists(f"datasets/{name}_{item['instance_id']}"):
            continue
        
        queries = [{
            "_id": item["instance_id"],
            "text": item["problem_statement"], 
            "metadata": {}
        }]
        
        try:
            structure = get_project_structure_from_scratch(item['repo'], item['base_commit'], 
                                                        item['instance_id'], 'playground')
            data = find_py_or_non_dict_with_path(structure['structure'], cond = item["instance_id"].startswith('pytest-dev__'))
            patch_info = parse_patch_full(item['patch'], structure)
        except:
            import pdb;pdb.set_trace()
        changed_funcs = set()
        for fle, hunks in patch_info.items():
            for hunk in hunks:
                if hunk['function_changed'] and hunk['newly_added'] is False:
                    if hunk['class_changed']:
                        changed_funcs.add(f'{fle}/{hunk["class_changed"]}/{hunk["function_changed"]}')
                    else:
                        changed_funcs.add(f'{fle}/{hunk["function_changed"]}')
        
        if not changed_funcs:
            #import pdb;pdb.set_trace()
            continue
        
        docs = []
        for func, content in data.items():
            docs.append({
                    "_id": func,
                    "title": '',
                    "text": content,
                    "metadata": {},
                })
        qrels = []
        for func in changed_funcs:
            try:
                assert func in data
            except:
                import pdb;pdb.set_trace()
            qrels.append({
                    "query-id": item["instance_id"],
                    "corpus-id": func,
                    "score": 1
                })
        
        path = os.path.join(args.dataset_dir, f"{name}_{item['instance_id']}")
        os.makedirs(path, exist_ok=True)
        os.makedirs(os.path.join(path, "qrels"), exist_ok=True)
        
        save_file_jsonl(queries, os.path.join(path, "queries.jsonl"))
        save_file_jsonl(docs, os.path.join(path, "corpus.jsonl"))
        qrels_path = os.path.join(path, "qrels", "test.tsv")
        save_tsv_dict(qrels, qrels_path, ["query-id", "corpus-id", "score"])

def main():
    dataset = datasets.load_dataset(args.dataset_name, cache_dir=args.cache_dir)[args.split]
    if args.num_examples is not None:
        import random
        indices = random.sample([i for i in range(len(dataset))], args.num_examples)
        dataset = dataset.select(indices)
    print(dataset)

    name = "swe-bench"
    if "lite" in args.dataset_name.lower():
        name += "-lite"
    elif 'verified' in args.dataset_name.lower():
        name += "-verified" 
    if args.split != 'test':
        name += f"-{args.split}"
    if args.level != 'file':
        name += f"-{args.level}"
    
    if not args.reuse_cached:
        [shutil.rmtree(f'{args.dataset_dir}/{instance}') for instance in os.listdir(f'{args.dataset_dir}') if instance.startswith(f'{name}_') or instance.startswith(f'csn_{args.level}_')]
    eval(args.level)(dataset, name)
    
    

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset_name", type=str, default="princeton-nlp/SWE-bench_Lite",
                        choices=["princeton-nlp/SWE-bench", "princeton-nlp/SWE-bench_Lite", "princeton-nlp/SWE-bench_Verified"])
    parser.add_argument("--split", type=str, default="test")
    parser.add_argument("--level", type=str, default="function")
    parser.add_argument("--cache_dir", type=str, default="cache/")
    parser.add_argument("--tmp_dir", type=str, default="tmp/")
    parser.add_argument("--dataset_dir", type=str, default="datasets")
    parser.add_argument("--num_examples", type=int, default=None)
    parser.add_argument("--reuse_cached", type=bool, default=True)
    args = parser.parse_args()

    main()
