from setuptools import setup, find_packages
from typing import List

requirement_lst:List[str] = []
def get_requirements() -> List[str]:
    try:
        with open("requirements.txt", "r") as f:
            lines=f.readlines()
            for line in lines:
                requirement=line.strip()
                if requirement and requirement!="-e .":
                    requirement_lst.append(requirement)
    except FileNotFoundError as e:
        print("requirements.txt file not found. Please make sure it exists.")

    return requirement_lst    

print(get_requirements())
setup(
    name="network_security",
    version="0.0.1",
    author="Urahara",
    author_email="email_",
    packages=find_packages(),
    install_requires=get_requirements()
)