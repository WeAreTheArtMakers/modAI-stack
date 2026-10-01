# LoRA training

This is real adapter training with `transformers`, `datasets`, and `peft`; it is not an Ollama Modelfile. Prompt/system configuration changes behavior at inference time, RAG supplies external knowledge at query time, LoRA learns a small set of adapter weights, and full fine-tuning updates the entire model. Run `python training/train_lora.py` on a machine with suitable model storage and compute. The adapter can later be loaded by a Transformers/vLLM serving stack or merged into a base model.
