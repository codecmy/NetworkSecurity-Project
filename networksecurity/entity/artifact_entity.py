from dataclasses import dataclass

@dataclass
class DataIngestionArtifacts:
    train_file_path:str
    test_file_path:str
    def __init__(self,train_file_path,test_file_path):
        self.train_file_path=train_file_path
        self.test_file_path=test_file_path
        