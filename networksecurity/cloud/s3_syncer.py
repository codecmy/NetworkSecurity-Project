import os
import subprocess
class S3Sync:
    def sync_folder_to_s3(self,folder,aws_bucket_url):
        command=f'aws s3 sync "{folder}" "{aws_bucket_url}"'
        subprocess.run(command, check=True)

    def sync_folder_from_s3(self,folder,aws_bucker_url):
        command=f'aws s3 sync "{aws_bucker_url}" "{folder}"'
        subprocess.run(command, check=True)
