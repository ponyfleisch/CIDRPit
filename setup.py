from model import CidrPitModel

if not CidrPitModel.exists():
    print("creating table")
    CidrPitModel.create_table(wait=True)