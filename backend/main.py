from fastapi import FastAPI 
app = FastAPI()

@app.get("/")
def home():
    return {"message": "Repo Ranger API"}

@app.get("/hello")
def agn():
    return {"Hello": "Again"}