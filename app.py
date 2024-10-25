from flask import Flask, request, jsonify, session, render_template, send_from_directory
import os
import yt_dlp
from flask_sqlalchemy import SQLAlchemy
import json
import time

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# SQLite 데이터베이스 설정
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 오디오 저장 폴더 경로 설정
AUDIO_FOLDER = 'audio'
if not os.path.exists(AUDIO_FOLDER):
    os.makedirs(AUDIO_FOLDER)

db = SQLAlchemy(app)

# User 모델 정의
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

# Playlist 모델 정의
class Playlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    songs = db.Column(db.Text, nullable=True)

# 애플리케이션 컨텍스트 내에서 데이터베이스 및 테이블 생성
with app.app_context():
    db.create_all()

# 홈 페이지
@app.route('/')
def home():
    return render_template('index.html')

# 사용자 등록
@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if User.query.filter_by(username=username).first():
        return jsonify({'error': '이미 존재하는 사용자 이름입니다.'}), 400

    new_user = User(username=username, password=password)
    db.session.add(new_user)
    db.session.commit()

    return jsonify({'message': '회원가입 성공!'})

# 로그인
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    user = User.query.filter_by(username=username, password=password).first()
    
    if user:
        session['user_id'] = user.id
        return jsonify({'message': '로그인 성공!'})
    else:
        return jsonify({'error': '아이디 또는 비밀번호가 잘못되었습니다.'}), 401

# 로그아웃
@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    return jsonify({'message': '로그아웃 성공!'})

# 로그인 상태 체크
@app.route('/check-login', methods=['GET'])
def check_login():
    if 'user_id' in session:
        return jsonify({'logged_in': True})
    return jsonify({'logged_in': False})

# 플레이리스트 생성
@app.route('/create-playlist', methods=['POST'])
def create_playlist():
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 403

    playlist_name = request.json.get('playlist_name')

    if not playlist_name:
        return jsonify({'error': '플레이리스트 이름을 입력하세요.'}), 400

    # 같은 이름의 플레이리스트가 있는지 확인
    existing_playlist = Playlist.query.filter_by(user_id=session['user_id'], name=playlist_name).first()
    if existing_playlist:
        return jsonify({'error': '이미 존재하는 플레이리스트입니다.'}), 400

    # 새로운 플레이리스트 생성
    new_playlist = Playlist(user_id=session['user_id'], name=playlist_name, songs=json.dumps([]))
    db.session.add(new_playlist)
    db.session.commit()

    return jsonify({'message': '플레이리스트 생성 완료!'})

# 오디오 다운로드 및 플레이리스트에 추가
@app.route('/convert', methods=['POST'])
def convert_audio():
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 403

    url = request.json.get('url')
    playlist_name = request.json.get('playlist_name')
    custom_name = request.json.get('audio_name')

    if not playlist_name:
        return jsonify({'error': '플레이리스트 이름을 입력하세요.'}), 400
    if not custom_name:
        return jsonify({'error': '파일 이름을 입력하세요.'}), 400

    # 사용자 ID 가져오기
    user_id = session['user_id']

    # 파일 이름에 확장자가 이미 있는지 확인 (예: .mp3)
    if custom_name.lower().endswith('.mp3'):
        custom_name = custom_name[:-4]  # ".mp3"를 제거하여 중복 방지

    # 사용자 ID를 포함한 고유 파일 이름 생성
    output_file_name = f"user{user_id}_{custom_name}.mp3"
    output_file_path = os.path.join(AUDIO_FOLDER, output_file_name)

    # 파일이 이미 존재하는지 확인하여 중복된 경우 새로운 이름 생성
    if os.path.exists(output_file_path):
        timestamp = int(time.time())  # 현재 타임스탬프 사용
        # 확장자 앞에 타임스탬프 추가 (예: user1_filename_123456789.mp3)
        output_file_name = f"user{user_id}_{custom_name}_{timestamp}.mp3"
        output_file_path = os.path.join(AUDIO_FOLDER, output_file_name)

    # yt-dlp 옵션 설정
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(AUDIO_FOLDER, f"user{user_id}_{custom_name}"),  # 확장자 없이 저장
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '320',
        }],
        'nocheckcertificate': True,  # 인증서 무시
    }

    # 다운로드 수행
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        return jsonify({'error': f'다운로드 오류: {str(e)}'}), 500

    # 다운로드된 파일을 리네임하여 최종적으로 고유한 이름으로 저장
    downloaded_file = os.path.join(AUDIO_FOLDER, f"user{user_id}_{custom_name}.mp3")
    if os.path.exists(downloaded_file):
        os.rename(downloaded_file, output_file_path)

    # 플레이리스트 가져오기
    playlist = Playlist.query.filter_by(user_id=user_id, name=playlist_name).first()

    if playlist is None:
        playlist = Playlist(user_id=user_id, name=playlist_name, songs=json.dumps([]))
        db.session.add(playlist)
        db.session.commit()

    try:
        songs = json.loads(playlist.songs) if playlist.songs else []
    except json.JSONDecodeError:
        songs = []

    songs.append(output_file_name)  # 파일명 업데이트
    playlist.songs = json.dumps(songs)
    db.session.commit()

    return jsonify({'message': '다운로드 완료!', 'filename': output_file_name})

# 플레이리스트 목록 반환
@app.route('/playlists', methods=['GET'])
def get_playlists():
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 403

    playlists = Playlist.query.filter_by(user_id=session['user_id']).all()
    result = {}

    for p in playlists:
        try:
            result[p.name] = json.loads(p.songs) if p.songs else []
        except json.JSONDecodeError:
            result[p.name] = []

    return jsonify(result)

# 오디오 파일 제공
@app.route('/audio/<filename>', methods=['GET'])
def serve_audio(filename):
    return send_from_directory(AUDIO_FOLDER, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000, debug=True)
