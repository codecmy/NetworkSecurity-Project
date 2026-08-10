from datetime import datetime
import os 
import sys 
import logging 

LOG_FILE=F"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

logs_path=os.path.join(os.getcwd(),"logs")
os.makedirs(logs_path,exist_ok=True)

LOG_FILE_PATH=os.path.join(logs_path,LOG_FILE)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH),
        logging.StreamHandler(sys.stdout),
    ],
)