# Kết quả benchmark LD-336 (chạy: python -m experiments.retrieval.benchmark --tune)

GloVe: 88% of the 232 index terms have a vector; loading took 1.9 s
| Method | Code R@4 | Code P@4 | Code MRR | Code nDCG@4 | Code noise | Docs R@3 | Docs P@3 | Docs MRR | Docs nDCG@3 | Docs noise | ms/file |
|---|---|---|---|---|---|---|---|---|---|---|---|
| tfidf, threshold 0.05 | 0.91 | 0.65 | 1.00 | 0.93 | 1.50 | 0.61 | 0.33 | 0.49 | 0.43 | 1.86 | 0.27 |
| tfidf, tuned threshold 0 | 0.91 | 0.65 | 1.00 | 0.93 | 1.79 | 0.63 | 0.36 | 0.49 | 0.45 | 1.93 | 0.38 |
| embedding (GloVe-100), threshold 0.8 | 0.69 | 0.52 | 0.78 | 0.67 | 1.36 | 0.33 | 0.19 | 0.38 | 0.32 | 0.86 | 1.61 |
| embedding (GloVe-100), tuned threshold 0.7 | 0.74 | 0.56 | 0.78 | 0.71 | 2.00 | 0.61 | 0.38 | 0.62 | 0.56 | 1.64 | 0.99 |
| hybrid (0.5 TF-IDF + 0.5 GloVe), threshold 0.45 | 0.91 | 0.65 | 0.92 | 0.89 | 1.00 | 0.44 | 0.24 | 0.57 | 0.47 | 0.71 | 1.33 |
| hybrid (0.5 TF-IDF + 0.5 GloVe), tuned threshold 0.35 | 0.91 | 0.65 | 0.92 | 0.89 | 1.79 | 0.67 | 0.38 | 0.85 | 0.68 | 1.86 | 0.78 |
