from pathlib import Path

class Config:
    def __init__(self, name):
        self.name = name

def load_config(path):
    return Config(Path(path).name)
