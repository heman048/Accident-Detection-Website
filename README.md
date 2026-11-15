# SafeRoad AI — Accident Detection Website

Blue-and-white academic web interface using HTML, CSS, JavaScript, Flask, YOLOv8 and SQLite.

## Important model note
The GitHub repository README describes training a custom accident detector and refers to `runs/detect/train/weights/best.pt`. The repository root also lists `yolov8s.pt`, which is the YOLOv8 small starting checkpoint. Do **not** assume that generic `yolov8s.pt` is an accident-trained model. This website expects the custom trained checkpoint at `models/best.pt`.

If the repository contains the trained checkpoint in its `runs/detect/.../weights/` directory, copy that `best.pt` into this project's `models/` folder. If it does not, the notebook may have saved the trained weights in the original author's Google Drive/Colab environment; you will need the exported trained checkpoint from that training run. The website cannot reproduce the custom training simply from the starting checkpoint.

## 1. Requirements
- Windows 10/11
- Python 3.10 or 3.11 recommended
- VS Code
- Trained accident-detection `best.pt` model file

## 2. Create and activate virtual environment (Windows PowerShell)
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```
If PowerShell blocks activation, use Command Prompt:
```cmd
venv\Scripts\activate.bat
```

## 3. Install dependencies
```bash
pip install -r requirements.txt
```
PyTorch/Ultralytics may take time to install. CPU inference works but can be slower. A compatible NVIDIA GPU can speed up inference.

## 4. Add the trained model
Copy the custom accident-trained `best.pt` file into:
```text
models/best.pt
```

## 5. Run the website
From the project root:
```bash
python backend/app.py
```
Open:
```text
http://127.0.0.1:5000
```

## 6. How to test
1. Open Image Detection and upload a road image.
2. Wait for inference; the annotated image appears below.
3. Open Video Detection and upload a short MP4 video.
4. Dashboard, history and alerts update from the SQLite database.

## API endpoints
- `GET /api/stats`
- `GET /api/history`
- `GET /api/alerts`
- `POST /api/detect/image` (multipart field: `file`)
- `POST /api/detect/video` (multipart field: `file`)
- `POST /api/alerts/<id>/resolve`

## Emergency alert limitation
This prototype creates an in-app alert record only. It does not send SMS, call emergency services, locate a vehicle, or dispatch responders. Every detection must be reviewed by a person. Do not present a model prediction as a confirmed accident.

## Detection assumption
The backend treats one or more model bounding boxes as a possible accident. This is valid only if the supplied checkpoint was trained to detect accident regions. If the model has different labels or inference behaviour, inspect its class names and adjust the decision rule in `backend/app.py`.

## Data and privacy
Uploaded files are deleted after processing; annotated outputs and analysis metadata remain locally. This is a classroom prototype and has not been security-hardened for public deployment.
