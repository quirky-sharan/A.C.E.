# S10 STT benchmark

25 recordings by sharan (audio kept local). WER / CER in %; HI WER~ = WER with Hinglish spelling variants forgiven (gaana / gana, chhota / chota, awaaz / avaaz); cmd % = the fast-path router makes the same decision as from the reference text, over the 5 English / 8 Hinglish phrases it understands today (a dropped transcript counts as wrong); asks % = "Did you say ...?" (confidence < 0.55); drops % = rejected by the guards ("I didn't catch that"); ms = transcription time per utterance; p95 total = VAD trim + transcription (NFR-1: ≤ 700 ms from the end of speech).

| Config | Device | EN WER | HI WER | HI WER~ | HI CER | EN cmd % | HI cmd % | asks % | drops % | median ms | p95 ms | p95 total ms | RTF | VRAM MB |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| turbo · auto | cuda int8_float16 | 0.0 | 47.7 | 44.3 | 21.7 | 100.0 | 37.5 | 20.0 | 0.0 | 502 | 542 | 545 | 0.212 | 1179 |
| turbo · en | cuda int8_float16 | 0.0 | 35.2 | 29.5 | 14.0 | 100.0 | 37.5 | 24.0 | 0.0 | 268 | 291 | 295 | 0.112 | 1096 |
| hinglish-swift · auto | cuda int8_float16 | 29.4 | 28.4 | 25.0 | 11.4 | 60.0 | 50.0 | 4.0 | 0.0 | 98 | 136 | 141 | 0.043 | 136 |
| hinglish-swift · en | cuda int8_float16 | 29.4 | 28.4 | 25.0 | 11.4 | 60.0 | 50.0 | 4.0 | 0.0 | 75 | 107 | 112 | 0.033 | 136 |
| hinglish-prime · auto | cuda int8_float16 | 23.5 | 19.3 | 15.9 | 6.3 | 60.0 | 62.5 | 0.0 | 0.0 | 732 | 903 | 908 | 0.315 | 1992 |
| hinglish-prime · en | cuda int8_float16 | 23.5 | 19.3 | 15.9 | 6.3 | 60.0 | 62.5 | 0.0 | 0.0 | 489 | 643 | 648 | 0.211 | 1992 |
| hinglish-trelis · auto | cuda int8_float16 | 0.0 | 125.0 | 125.0 | 62.6 | 100.0 | 0.0 | 4.0 | 0.0 | 879 | 1248 | 1253 | 0.393 | 1992 |
| hinglish-trelis · en | cuda int8_float16 | 0.0 | 119.3 | 119.3 | 61.1 | 100.0 | 0.0 | 4.0 | 0.0 | 619 | 1104 | 1109 | 0.283 | 1992 |
| small · en · CPU | cpu int8 | 0.0 | 43.2 | 38.6 | 14.9 | 100.0 | 50.0 | 12.0 | 0.0 | 2400 | 2480 | 2485 | 1.007 | 0 |
| swift · en · CPU | cpu int8 | 29.4 | 35.2 | 31.8 | 14.4 | 60.0 | 25.0 | 4.0 | 0.0 | 747 | 787 | 792 | 0.314 | 0 |
| turbo · en · CPU | cpu int8 | 0.0 | 48.9 | 40.9 | 21.7 | 100.0 | 25.0 | 32.0 | 0.0 | 10027 | 10275 | 10279 | 4.207 | 0 |
