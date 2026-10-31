# Five-minute demo script (Phase 1)

A fixed walkthrough for the Project-A evaluation. Every step uses the bundled sample
`demo_mixed_2k.csv` (1,987 held-out CIC-IDS2017 flows), so the numbers below repeat exactly.

## Before the panel arrives

1. `ollama serve` is running and `ollama list` shows `qwen2.5:3b`.
2. `python run.py`, then open http://127.0.0.1:8000.
3. Optional clean slate: stop the server, delete `backend/data/nids.db`, start again.
4. Type your name into the decision box once, so it is remembered.

## The walkthrough

| Time | Page | Do | Say |
|---|---|---|---|
| 0:00 | Analyze | Point at the model switch and the sample list | Three detectors were trained on de-duplicated CIC-IDS2017 data. The samples were never seen in training. |
| 0:30 | Analyze | Click **Analyze** on *Mixed week* | 1,987 flows are scored in about 20 ms. 479 are flagged. |
| 1:00 | Results | Walk the stat strip, then *Flagged flows by file label* | The file's labels are only used to check us: precision 0.985, recall 0.804, 0.5% false alarms. Web attacks are the blind spot. |
| 1:45 | Alerts | Click **Review 479 alerts**, open record 770 | All three models agree. *Why it was flagged* shows the five features furthest from normal traffic. |
| 2:30 | Alerts | Click **Write draft** | A 3-billion-parameter model runs on this laptop's GPU and writes the advisory in about 5 seconds. It only sees the score and the deviations. |
| 3:15 | Alerts | **Edit draft**, change a step, **Approve** | The analyst decides. Nothing is blocked automatically. |
| 3:45 | Audit | Open the decision, then **View draft** | Every prompt, model output and decision is stored. |
| 4:15 | Models | Threshold explorer, then *Attacks never seen in training* | The threshold is chosen on validation data at 1% false alarms. On new attack types F1 drops to 0.61, which is why Phase 2 adds a zero-day detector. |
| 4:45 | System | Show the draft-writer chain | If the model is unavailable, the offline playbook takes over. |

## Offline fallback (show it, or use it if the model fails)

- On any alert, click **Use offline playbook**. A complete draft appears instantly with no language model.
- To show it end to end: stop Ollama (`taskkill /im ollama.exe /f`) and click **Write again**.
  The draft is written by the offline playbook and the page says so.
- The app uses no internet connection: fonts, models and the knowledge base are all local.
  Only the "Read the full entry" links in Knowledge open external pages.

## Numbers to have ready

| | Value | Source |
|---|---|---|
| Best held-out F1 | 0.989 (Random Forest), 0.982 (neural network) | `artifacts/tables/model_comparison.md` |
| False alarm rate at threshold | 0.13% RF, 0.34% NN | same |
| F1 on unseen attack types | 0.61 NN, 0.29 RF, 0.75 LR | `artifacts/tables/temporal_split.md` |
| Duplicates removed before splitting | 1,000,378 of 2,830,743 flows | `artifacts/data_card.json` |
| Knowledge-base search, top five | 18 of 20 test questions | `artifacts/kb/retrieval_eval.json` |
| Draft time | about 5 s, first words under 1 s | System page |
