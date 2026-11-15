# Kết quả benchmark LD-337 (chạy: python -m experiments.retrieval.benchmark)

GloVe: 98% of the 220 index terms have a vector; loading took 2.0 s
| Method | Code R@4 | Code P@4 | Code MRR | Code nDCG@4 | Code noise | Docs R@3 | Docs P@3 | Docs MRR | Docs nDCG@3 | Docs noise | ms/file |
|---|---|---|---|---|---|---|---|---|---|---|---|
| tfidf, threshold 0.05 | 0.91 | 0.65 | 1.00 | 0.92 | 1.50 | 0.73 | 0.43 | 0.61 | 0.58 | 1.64 | 0.33 |
| LD-337 path filter only, threshold 0.05 | 0.91 | 0.65 | 1.00 | 0.92 | 1.50 | 0.70 | 0.40 | 0.93 | 0.75 | 1.00 | 0.34 |
| LD-337 call bonuses only, threshold 0.05 | 0.96 | 0.69 | 1.00 | 0.96 | 1.36 | 0.73 | 0.43 | 0.61 | 0.58 | 1.64 | 0.40 |
| LD-337 (production), threshold 0.05 | 0.96 | 0.69 | 1.00 | 0.96 | 1.36 | 0.70 | 0.40 | 0.93 | 0.75 | 1.00 | 0.40 |
| embedding (GloVe-100), threshold 0.8 | 0.67 | 0.50 | 0.75 | 0.66 | 1.43 | 0.37 | 0.21 | 0.38 | 0.34 | 0.93 | 1.05 |
| hybrid (0.5 TF-IDF + 0.5 GloVe), threshold 0.45 | 0.91 | 0.65 | 0.92 | 0.88 | 1.14 | 0.50 | 0.31 | 0.68 | 0.53 | 0.71 | 0.97 |
