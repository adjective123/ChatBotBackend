# main.py - Backend Server
# !uvicorn main:app --reload --port 5000

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from datetime import datetime
import time
from typing import List, Optional
from sqlalchemy import create_engine, Column, String, Integer, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

# import get_tts
import audiotest_api.judgeTest.tts_test as tts_test

app = FastAPI()

USER_ID = 10

# ✅ CORS 설정 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "http://localhost:8002",
        "http://127.0.0.1:8002",
    ],  # 허용할 origin 목록
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용 (GET, POST, OPTIONS 등)
    allow_headers=["*"],  # 모든 헤더 허용
)

# 공유할 전역 변수
class SharedData:
    user_id = None
    input_wav = None
    atot_text = None
    ttot_text = None

SQLALCHEMY_DATABASE_URL = 'sqlite:///./users.db'
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class UserDB(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True, unique=True)
    input_wav_list = Column(JSON, index=True)
    atot_text_list = Column(JSON, index=True)
    ttot_text_list = Column(JSON, index=True)
    output_wav_list = Column(JSON, index=True)

class UserData(BaseModel):
    id: int
    input_wav_list: Optional[List[Optional[str]]] = []
    atot_text_list: Optional[List[Optional[str]]] = []
    ttot_text_list: Optional[List[Optional[str]]] = []
    output_wav_list: Optional[List[Optional[str]]] = []
    
    class Config:
        from_attributes = True

class IncomingMessage(BaseModel):
    message_id: int
    room_id: str
    text: str
    client_type: str

class ProcessedResult(BaseModel):
    message_id: int
    processed_text: str

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get('/')
async def read_root(db: Session=Depends(get_db)):
    """Backend 서버 루트 엔드포인트 - 사용자 조회/생성"""
    try:
        db_user = db.query(UserDB).filter(UserDB.id==USER_ID).first()
        
        if db_user is None:
            # 새 사용자 생성
            db_user = UserDB(
                id=USER_ID, 
                input_wav_list=[], 
                atot_text_list=[], 
                ttot_text_list=[], 
                output_wav_list=[]
            )
            db.add(db_user)
            db.commit()  # ✅ 새로 생성한 경우에만 commit
            db.refresh(db_user)
            print(f"✅ 새 사용자 생성: ID={USER_ID}")
        else:
            print(f"✅ 기존 사용자 조회: ID={USER_ID}")
        
        # None 값을 빈 리스트로 변환 (안전한 처리)
        return {
            "message": "This is the Backend Server", 
            "user": {
                "id": USER_ID, 
                "input_wav_list": db_user.input_wav_list or [], 
                "atot_text_list": db_user.atot_text_list or [], 
                "ttot_text_list": db_user.ttot_text_list or [], 
                "output_wav_list": db_user.output_wav_list or []
            }
        }
        
    except Exception as e:
        # 에러 로깅
        print(f"❌ 루트 엔드포인트 오류: {str(e)}")
        db.rollback()  # 에러 발생 시 롤백
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")

@app.get('/users', response_model=List[UserData])
async def get_users(db: Session=Depends(get_db)):
    """모든 사용자 조회"""
    try:
        users = db.query(UserDB).all()
        # None 값을 빈 리스트로 안전하게 변환
        for user in users:
            user.input_wav_list = user.input_wav_list or []
            user.atot_text_list = user.atot_text_list or []
            user.ttot_text_list = user.ttot_text_list or []
            user.output_wav_list = user.output_wav_list or []
        return users
    except Exception as e:
        print(f"❌ /users 엔드포인트 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=f"사용자 조회 실패: {str(e)}")

@app.get('/users/{user_id}', response_model=UserData)
async def get_user(user_id: int, db: Session=Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.id==user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.get('/users/{user_id}/atot')
async def upload_atot(user_id: int, db: Session=Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.id==user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user.id, "atot_text": user.atot_text_list}
  
@app.get('/users/{user_id}/ttot')
async def get_user_ttot(user_id: int, db: Session=Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.id==user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user.id, "ttot_text": user.ttot_text_list}

@app.get("/atot")
async def get_atot():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://1.20.15.20:8000/run-model")
            response.raise_for_status()
            
            data = response.json()
            
            # 전역 변수에 저장
            SharedData.user_id = data.get("user_id")
            SharedData.atot_text = data.get("result", {}).get("details", {}).get("received_text", None)
            SharedData.input_wav = data.get("result", {}).get("details", {}).get("audio_url", None)
            
            return {"user_id": SharedData.user_id, "input_wav": SharedData.input_wav, "atot_text": SharedData.atot_text}
    except httpx.RequestError as e:
        return {"error": f"atot 서버에 연결할 수 없습니다: {str(e)}"}
    except Exception as e:
        return {"error": f"알 수 없는 오류: {str(e)}"}

@app.get("/ttot")
async def get_ttot():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://20.20.15.20:8000/generate")
            response.raise_for_status()
            
            data = response.json()
            
            # 전역 변수에 저장
            SharedData.ttot_text = data.get("response")
            return {"user_id": data.get("user_id"), "ttot_text": SharedData.ttot_text}
    except httpx.RequestError as e:
        return {"error": f"ttot 서버에 연결할 수 없습니다: {str(e)}"}
    except Exception as e:
        return {"error": f"알 수 없는 오류: {str(e)}"}

@app.post("/process-audio")
async def process_audio(db: Session=Depends(get_db)):
    """저장된 데이터를 사용해 TTS 처리"""
    
    if SharedData.ttot_text is None:
        return {"error": "ttot_text가 없습니다. 먼저 /ttot을 호출하세요"}
    
    # DB 조회
    user = db.query(UserDB).filter(UserDB.id==USER_ID).first()
    if user is None:
        return {"error": f"User {USER_ID}를 찾을 수 없습니다."}
    
    # TTS 처리 변수 초기화
    output_filename = None
    tts_success = False
    tts_error = None
    
    # TTS 서버에 요청 (실패해도 계속 진행)
    try:
        # wav_file_data = get_tts.get_tts_audio(SharedData.ttot_text, language='ko')
        async with httpx.AsyncClient(timeout=30.0) as client:
            tts_response = await client.post(
                "http://20.20.15.1:8000/generate-speech/",
                json={"request_text": SharedData.ttot_text},
                headers={"Content-Type": "application/json"}
            )
            tts_response.raise_for_status()
            wav_file_data = tts_response.content
        
        if wav_file_data and len(wav_file_data) > 0:
            output_filename = "received_audio.wav"
            with open(output_filename, 'wb') as f:
                f.write(wav_file_data)
            tts_success = True
            print(f"✅ TTS 성공: {output_filename}, 크기: {len(wav_file_data)} bytes")
        else:
            tts_error = "TTS 서버에서 빈 데이터를 받았습니다."
            print(f"⚠️ TTS 실패: {tts_error}")
            
    except httpx.ConnectError as e:
        tts_error = f"TTS 서버 연결 실패 (port 8004가 실행 중인지 확인): {str(e)}"
        print(f"❌ {tts_error}")
    except httpx.HTTPStatusError as e:
        tts_error = f"TTS API 오류 (상태 코드: {e.response.status_code}): {str(e)}"
        print(f"❌ {tts_error}")
    except Exception as e:
        tts_error = f"TTS 오류: {str(e)}"
        print(f"❌ TTS 예외: {tts_error}")
    
    # ✅ TTS 성공 여부와 관계없이 DB에 저장
    if SharedData.input_wav:
        user.input_wav_list = (user.input_wav_list or []) + [SharedData.input_wav]
    else:
        user.input_wav_list = (user.input_wav_list or []) + [None]

    user.atot_text_list = (user.atot_text_list or []) + [SharedData.atot_text or ""]
    user.ttot_text_list = (user.ttot_text_list or []) + [SharedData.ttot_text or ""]
    
    # output_wav는 있으면 추가, 없으면 None 또는 빈 문자열 추가
    if output_filename:
        user.output_wav_list = (user.output_wav_list or []) + [output_filename]
    else:
        user.output_wav_list = (user.output_wav_list or []) + [None]
    
    db.commit()
    db.refresh(user)
    
    # 응답 생성
    response = {
        "user_id": user.id,
        "input_wav": SharedData.input_wav,
        "atot_text": SharedData.atot_text,
        "ttot_text": SharedData.ttot_text,
        "output_wav": output_filename,
        "output_wav_list": user.output_wav_list,
        "tts_success": tts_success
    }
    
    if tts_success:
        response["message"] = f"✅ 성공! TTS 오디오를 '{output_filename}'로 저장했습니다."
    else:
        response["message"] = f"⚠️ 데이터는 저장했지만 TTS 생성 실패"
        response["tts_error"] = tts_error
    
    return response

# ✅ 새로 추가: 전체 파이프라인 통합 엔드포인트
@app.post("/run-full-pipeline")
async def run_full_pipeline(db: Session=Depends(get_db)):
    """
    전체 파이프라인 실행 (모든 단계를 순차적으로):
    1. ATOT 서버에서 음성→텍스트 변환 결과 가져오기
    2. TTOT 서버에서 텍스트→텍스트 생성
    3. TTS로 음성 생성
    4. DB에 모든 데이터 저장
    """
    result = {
        "step1_atot": None,
        "step2_ttot": None,
        "step3_tts": None,
        "success": False,
        "errors": []
    }
    
    print("\n" + "="*60)
    print("🚀 전체 파이프라인 시작")
    print("="*60)
    
    # ====== STEP 1: ATOT (음성→텍스트) ======
    print("\n1️⃣  ATOT 서버 호출 중...")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            atot_response = await client.get("http://1.20.15.20:8000/run-model")
            atot_response.raise_for_status()
            atot_data = atot_response.json()
            
            SharedData.atot_text = atot_data.get("result", {}).get("details", {}).get("received_text", None)
            SharedData.input_wav = atot_data.get("result", {}).get("details", {}).get("audio_url", None)
            
            result["step1_atot"] = {
                "success": True,
                "user_id": atot_data.get("user_id"),
                "input_wav": SharedData.input_wav,
                "atot_text": SharedData.atot_text
            }
            print(f"✅ ATOT 완료: {SharedData.atot_text}")
            
    except Exception as e:
        error_msg = f"ATOT 실패: {str(e)}"
        print(f"❌ {error_msg}")
        result["errors"].append(error_msg)
        result["step1_atot"] = {"success": False, "error": error_msg}
        return result  # ATOT 실패하면 여기서 중단
    
    # ====== STEP 2: TTOT (텍스트→텍스트) ======
    print("\n2️⃣  TTOT 서버 호출 중...")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            ttot_response = await client.get("http://20.20.15.20:8000/generate")
            ttot_response.raise_for_status()
            ttot_data = ttot_response.json()
            
            SharedData.ttot_text = ttot_data.get("response")
            
            result["step2_ttot"] = {
                "success": True,
                "user_id": ttot_data.get("user_id"),
                "ttot_text": SharedData.ttot_text
            }
            print(f"✅ TTOT 완료: {SharedData.ttot_text}")
            
    except Exception as e:
        error_msg = f"TTOT 실패: {str(e)}"
        print(f"❌ {error_msg}")
        result["errors"].append(error_msg)
        result["step2_ttot"] = {"success": False, "error": error_msg}
        return result  # TTOT 실패하면 여기서 중단
    
    # ====== STEP 3: TTS + DB 저장 ======
    print("\n3️⃣  TTS 처리 및 DB 저장 중...")
    
    if SharedData.ttot_text is None:
        error_msg = "ttot_text가 비어있습니다"
        print(f"❌ {error_msg}")
        result["errors"].append(error_msg)
        result["step3_tts"] = {"success": False, "error": error_msg}
        return result
    
    # DB 조회
    user = db.query(UserDB).filter(UserDB.id==USER_ID).first()
    if user is None:
        error_msg = f"User {USER_ID}를 찾을 수 없습니다"
        print(f"❌ {error_msg}")
        result["errors"].append(error_msg)
        return result
    
    # TTS 처리
    output_filename = None
    tts_success = False
    tts_error = None
    
    try:
        # wav_file_data = get_tts.get_tts_audio(SharedData.ttot_text, language='ko')
        async with httpx.AsyncClient(timeout=30.0) as client:
            tts_response = await client.post(
                "http://20.20.15.1:8000/generate-speech/",
                json={"request_text": SharedData.ttot_text},
                headers={"Content-Type": "application/json"}
            )
            tts_response.raise_for_status()
            wav_file_data = tts_response.content
        
        if wav_file_data and len(wav_file_data) > 0:
            # import time as time_module
            # output_filename = f"received_audio_{USER_ID}_{int(time_module.time())}.wav"
            output_filename = "received_audio.wav"
            with open(output_filename, 'wb') as f:
                f.write(wav_file_data)
            tts_success = True
            print(f"✅ TTS 성공: {output_filename}, 크기: {len(wav_file_data)} bytes")
        else:
            tts_error = "TTS 서버에서 빈 데이터를 받았습니다"
            print(f"⚠️ {tts_error}")
            
    except httpx.ConnectError as e:
        tts_error = f"TTS 서버 연결 실패 (port 8004 확인): {str(e)}"
        print(f"❌ {tts_error}")
    except httpx.HTTPStatusError as e:
        tts_error = f"TTS API 오류 (상태: {e.response.status_code})"
        print(f"❌ {tts_error}")
    except Exception as e:
        tts_error = f"TTS 오류: {str(e)}"
        print(f"❌ {tts_error}")
    
    # DB 저장 (TTS 실패해도 저장)
    if SharedData.input_wav:
        user.input_wav_list = (user.input_wav_list or []) + [SharedData.input_wav]
    else:
        user.input_wav_list = (user.input_wav_list or []) + [None]
    
    user.atot_text_list = (user.atot_text_list or []) + [SharedData.atot_text or ""]
    user.ttot_text_list = (user.ttot_text_list or []) + [SharedData.ttot_text or ""]
    
    if output_filename:
        user.output_wav_list = (user.output_wav_list or []) + [output_filename]
    else:
        user.output_wav_list = (user.output_wav_list or []) + [None]
    
    db.commit()
    db.refresh(user)
    
    result["step3_tts"] = {
        "success": tts_success,
        "output_wav": output_filename,
        "tts_error": tts_error
    }
    
    result["success"] = True
    result["user_id"] = USER_ID
    result["final_data"] = {
        "input_wav": SharedData.input_wav,
        "atot_text": SharedData.atot_text,
        "ttot_text": SharedData.ttot_text,
        "output_wav": output_filename
    }
    
    print("\n" + "="*60)
    print("✅ 전체 파이프라인 완료!")
    print("="*60)
    
    return result

# 클라이언트에서 호출 순서:
# 방법 1 (기존): 
#   1. GET /atot -> 2. GET /ttot -> 3. POST /process-audio
# 방법 2 (새로운, 추천):
#   1. ATOT 서버에서 POST /run-model 실행
#   2. POST /run-full-pipeline (모든 단계 자동 처리)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=5000)