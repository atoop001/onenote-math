# M4 personal tuning results

**Tuned model: Accepted.** Gate: tuned zero-fix and ≤2-fix rates at least the base's, and warm median latency at most 1.15× the base's.

- Test set: 60 problems (the user's handwriting, local only). Tune set: 60 problems.
- Timing: warm read on the dev CPU (GPU not used), model only, median over the test set.

| Model | Zero fixes | ≤2 fixes | Median ms |
|---|---|---|---|
| Base (untuned) | 93% | 98% | 1105 |
| Tuned | 97% | 100% | 1052 |

By area (zero fixes / ≤2 fixes):

- Base (untuned): algebra 93% / 100%, calc1 87% / 100%, calc2 100% / 100%, precalc 90% / 90%
- Tuned: algebra 100% / 100%, calc1 93% / 100%, calc2 100% / 100%, precalc 90% / 100%

## Low-confidence threshold

Threshold **0.99**: flags 50% of misread symbols and 4% of all symbols (target: ≥90% of misreads, at most 20% of symbols). A misread is a symbol that differs from the expected answer in a problem the scorer says needs fixes; LaTeX syntax pieces (braces, ^, _) never count.

Measured on 2 misread symbols in the whole test set, so the recall figure is a rough guide. Real corrections collected from M5 on will refine it.

## Training log

```
samples=60 epochs=15 lr=1e-05 batch=4 views=8 seed=7 device=cuda
epoch 1: loss 1.5734 (27 s)
epoch 2: loss 0.0101 (53 s)
epoch 3: loss 0.0058 (79 s)
epoch 4: loss 0.0005 (104 s)
epoch 5: loss 0.0007 (131 s)
epoch 6: loss 0.0004 (159 s)
epoch 7: loss 0.0002 (185 s)
epoch 8: loss 0.0001 (211 s)
epoch 9: loss 0.0001 (237 s)
epoch 10: loss 0.0001 (262 s)
epoch 11: loss 0.0001 (288 s)
epoch 12: loss 0.0002 (315 s)
epoch 13: loss 0.0003 (341 s)
epoch 14: loss 0.0001 (367 s)
epoch 15: loss 0.0001 (392 s)
```
