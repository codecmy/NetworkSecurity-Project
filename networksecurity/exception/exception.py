import sys
from networksecurity.logging import logger
class NetworkSecurityException(Exception):
    def __init__(self, error_message,error_details:sys):
        self.error_message =error_message
        _,_,exc_tb=error_details.exc_info()
        file_name=exc_tb.tb_frame.f_code.co_filename
        self.lineno=exc_tb.tb_lineno

    def __str__(self):
        return f"Error occurred in script: [{self.error_message}] at line number: [{self.lineno}]"    


if __name__=="__main__":
    try:
        logger.logging.info("This is an info message")
        a=1/0
        print("This will not be printed",a)
    except Exception as e:
        raise NetworkSecurityException(e,sys)