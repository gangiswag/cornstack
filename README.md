# 🌽 CoRNStack: A High-Quality Contrastive Dataset for Better Code Ranking.

<p align="left">
    ℹ️&nbsp;<a href="#-about">About</a>
    | 📖&nbsp;<a href="#-more-about-cornstack">More About CORNSTACK</a>
    | 🚀&nbsp;<a href="#-quick-start">Quick Start</a>
    | 👀&nbsp;<a href="#-running-evaluation">Running Evaluation</a>
    | 🔄&nbsp;<a href="#-running-reranker">Running Reranker</a>
</p>



## ℹ️ About
* 🌽 **CoRNStack** is a large-scale high-quality (text, code) pairs dataset for training and fine-tuning embedding models and re-rankers for code retrieval via contrastive learning. 
* We train **CodeRankEmbed**, a 137M bi-encoder, on 🌽 **CoRNStack** and demonstrate considerably higher performance on a variety of code retrieval benchmarks, with substantial gains over current state-of-the-art code embedding models.
* By leveraging 🌽 **CoRNStack**, we are the first to finetune LLMs as code rerankers. **CodeRankLLM**, our 7B code reranker, considerably improves performance over the retriever.


## 📖 More About CORNSTACK

The performance of code embedding models is highly contingent on the quality of the large-scale data used for contrastive training. Effective contrastive training hinges on satisfying two primary conditions: 
1) The positives are highly relevant to the query and not noisy
2) The negatives are semantically similar to the positives but do not directly address the query, a.k.a hard negatives.

Existing approaches heuristically source contrastive examples from large-scale open-source code data with limited filtering and mining, retaining irrelevant or incorrectly labeled <query, positive> pairs, which impair the models’ ability to learn robust and accurate representations. To address these challenges, we introduce curriculum-based hard negative mining and consistency filtering techniques and apply these techniques on the de-duplicated version of The Stack v2. More details on these specific curation techniques and how we use them to train embedding models and re-rankers in our paper coming soon!

## 🚀 Quick Start

Install the required dependencies:
```bash
pip install -r requirements.txt
```


## 👀 Running Evaluation

To reproduce the performance of **CodeRankEmbed** on popular code retrieval benchmarks, run the following commands: 

### COIR Evaluation
```
cd src/
python evaluation/eval_coir.py
```

### CSN Evaluation

```
cd src/
python create/csn.py
python evaluation/eval_csn.py
```
Ignore any errors when running `python create/csn.py`.

### SWE-Bench-Lite Evaluation

```
cd src/
python create/swebench.py
python evaluation/eval_swebench.py
python evaluation/eval_localization.py --level file  #print out file localization top-k results
python evaluation/eval_localization.py --level function  #print out function localization top-k results
```

## 🔄 Running Reranker

Initialize and update the submodules:
```bash
# Initialize submodules
git submodule init
git submodule update
```
**Note:** You need to install the vLLM library (instructions [here](https://docs.vllm.ai/en/latest/getting_started/installation.html)) which provides optimization for LLM inference.

To run the complete pipeline including retrieval and reranking:

```bash
cd src/
./run_pipeline.sh
```

The pipeline script supports several options:
- `--dataset_dir`: Directory for datasets (default: ./datasets)
- `--output_dir`: Directory for outputs (default: ./outputs)
- `--eval_dir`: Directory for evaluation results (default: ./evaluations)
- `--top_k`: Number of candidates to rerank (default: 100)
- `--window_size`: Window size for reranking (default: 10)
- `--step_size`: Step size for reranking (default: 5)
- `--skip_retriever`: Skip retrieval step if you already have retrieval results (default: 1)

The pipeline will:
1. Run the retriever to generate initial rankings (if --skip_retriever=0)
2. Convert the retrieval results to the required format
3. Run the CodeRankLLM reranker on the top retrieved results
4. Evaluate and save the reranking results

Results will be saved in:
- Reranking outputs: `{output_dir}/code_datasets/{dataset_name}/`
- Evaluation results: `{eval_dir}/eval_results/{dataset_name}_eval.json`

We plan to release the full training and dataset curation code soon!

## Citation

If this repo was useful to you, please consider citing our work:
```
@inproceedings{sureshcornstack,
  title={CoRNStack: High-Quality Contrastive Data for Better Code Retrieval and Reranking},
  author={Suresh, Tarun and Reddy, Revanth Gangi and Xu, Yifei and Nussbaum, Zach and Mulyar, Andriy and Duderstadt, Brandon and Ji, Heng},
  booktitle={The Thirteenth International Conference on Learning Representations},
  year={2025}
}
```

