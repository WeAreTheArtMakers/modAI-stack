from dataclasses import dataclass
@dataclass
class LoRAConfig:
    model_name: str = "distilgpt2"
    output_dir: str = "./artifacts/lora"
    r: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    learning_rate: float = 2e-4
    epochs: int = 1
    target_modules: tuple[str, ...] = ("c_attn",)
