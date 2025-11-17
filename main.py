from fastapi import FastAPI, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from passlib.context import CryptContext
import jwt
from fastapi.security import HTTPBearer
import google.generativeai as genai
import json
import os
from dotenv import load_dotenv


load_dotenv()

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------
# CONFIG
# ---------------------
client = AsyncIOMotorClient("mongodb+srv://Winter:scarjo%4055435@cluster0.uppfsqy.mongodb.net/?appName=Cluster0")
db = client["quiz_app"]
users_col = db["users"]

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
SECRET_KEY = "j23nfd92nf923nf92309f23nf923nf9230f"

# Gemini API
GEMINI_KEY = os.getenv("GEMINI_KEY")
genai.configure(api_key=GEMINI_KEY)

# XP rules
XP_MAP = {
    "easy": 50,
    "medium": 70,
    "hard": 100
}

# ---------------------
# VERIFY TOKEN
# ---------------------
def verify_token(credentials=Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ---------------------
# SIGNUP
# ---------------------
@app.post("/signup")
async def signup(username: str = Form(...), email: str = Form(...), password: str = Form(...)):
    if await users_col.find_one({"email": email}):
        return {"status": "fail", "msg": "Email already registered"}

    hashed = pwd.hash(password)

    await users_col.insert_one({
        "username": username,
        "email": email,
        "password": hashed,
        "xp": 0,
        "quizzes_taken": 0,
        "accuracy": 0  # stored as % later
    })

    return {"status": "success", "msg": "Account created!"}


# ---------------------
# LOGIN
# ---------------------
@app.post("/login")
async def login(email: str = Form(...), password: str = Form(...)):
    user = await users_col.find_one({"email": email})
    if not user:
        return {"status": "fail", "msg": "User not found"}

    if not pwd.verify(password, user.get("password")):
        return {"status": "fail", "msg": "Wrong password"}

    token = jwt.encode(
        {"email": email, "username": user["username"]},
        SECRET_KEY,
        algorithm="HS256"
    )

    return {"status": "success", "token": token}


# ---------------------
# QUIZ GENERATION (GEMINI)
# ---------------------
@app.post("/generate_quiz")
async def generate_quiz(
    topic: str = Form(...),
    difficulty: str = Form(...),
    num_questions: int = Form(...),
    user=Depends(verify_token)
):
    model = genai.GenerativeModel("gemini-2.5-flash")

    prompt = f"""
    Generate a {difficulty} level multiple choice quiz on:

    Topic: {topic}
    Number of questions: {num_questions}

    Return ONLY JSON.
    Do NOT add explanations or markdown.
    Follow EXACT structure:

    {{
        "questions": [
            {{
                "question": "string",
                "options": ["A","B","C","D"],
                "correct_answer": "A"
            }}
        ]
    }}
    """

    response = await model.generate_content_async(prompt)

    text = response.text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    json_str = text[start:end]

    try:
        quiz_json = json.loads(json_str)
    except:
        raise HTTPException(status_code=500, detail="AI returned invalid JSON")

    return {"status": "success", "quiz": quiz_json}


# ======================================================
#     UPDATE XP AFTER QUIZ SUBMISSION
# ======================================================
@app.post("/update_xp")
async def update_xp(
    difficulty: str = Form(...),
    score: int = Form(...),  # score out of total questions
    user=Depends(verify_token)
):

    email = user["email"]
    user_data = await users_col.find_one({"email": email})

    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    # XP gain
    xp_gain = XP_MAP.get(difficulty.lower(), 50)

    new_xp = user_data["xp"] + xp_gain
    quizzes = user_data["quizzes_taken"] + 1

    # Calculate new accuracy
    # accuracy = total score / quizzes (average score)
    old_acc = user_data["accuracy"]
    new_accuracy = ((old_acc * user_data["quizzes_taken"]) + score) / quizzes

    await users_col.update_one(
        {"email": email},
        {"$set": {
            "xp": new_xp,
            "quizzes_taken": quizzes,
            "accuracy": new_accuracy
        }}
    )

    return {
        "status": "success",
        "msg": "XP updated",
        "new_xp": new_xp
    }


# ======================================================
#     LEADERBOARD (SORT BY XP DESC)
# ======================================================
@app.get("/leaderboard")
async def leaderboard():
    all_users = await users_col.find({}, {"_id": 0, "password": 0}).to_list(length=None)

    # Add missing XP fields to old users so no KeyError occurs
    for u in all_users:
        u.setdefault("xp", 0)
        u.setdefault("quizzes_taken", 0)
        u.setdefault("accuracy", 0)

    # Sort by XP
    sorted_users = sorted(all_users, key=lambda x: x["xp"], reverse=True)

    # Add rank numbers
    for i, user in enumerate(sorted_users, start=1):
        user["rank"] = i

    return {"status": "success", "leaderboard": sorted_users}

# ============================
#   USER PROFILE (/me)
# ============================
@app.get("/me")
async def get_profile(user=Depends(verify_token)):
    email = user["email"]
    user_data = await users_col.find_one({"email": email}, {"_id": 0, "password": 0})

    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    # Provide defaults if missing
    user_data.setdefault("xp", 0)
    user_data.setdefault("quizzes_taken", 0)
    user_data.setdefault("accuracy", 0)
    user_data.setdefault("streak", 0)

    return {"status": "success", "user": user_data}
