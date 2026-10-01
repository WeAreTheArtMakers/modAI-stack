"""Actual PEFT/LoRA example. Run separately from the API: python training/train_lora.py."""
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
from peft import LoraConfig, TaskType, get_peft_model
from training.config import LoRAConfig
def main():
    cfg = LoRAConfig(); tokenizer = AutoTokenizer.from_pretrained(cfg.model_name); tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(cfg.model_name)
    model = get_peft_model(model, LoraConfig(r=cfg.r, lora_alpha=cfg.lora_alpha, lora_dropout=cfg.lora_dropout, target_modules=list(cfg.target_modules), task_type=TaskType.CAUSAL_LM))
    data = Dataset.from_list([{"text": "### Instruction: Explain RAG\n### Response: Retrieval augments generation with relevant context."}])
    def tokenize(x): return tokenizer(x["text"], truncation=True, padding="max_length", max_length=128)
    tokenized = data.map(tokenize, batched=True); args = TrainingArguments(output_dir=cfg.output_dir, learning_rate=cfg.learning_rate, num_train_epochs=cfg.epochs, per_device_train_batch_size=1, report_to=[])
    Trainer(model=model, args=args, train_dataset=tokenized).train(); model.save_pretrained(cfg.output_dir); tokenizer.save_pretrained(cfg.output_dir)
if __name__ == "__main__": main()
