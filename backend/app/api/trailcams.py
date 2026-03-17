from __future__ import annotations
from fastapi import APIRouter

router = APIRouter()

# TODO: replace with your real trailcam list source
@router.get("/trailcams")
def list_trailcams():
    return [
        {"id": "cam_1","name":"Big Field West End","make":"Tactacam","model":"Reveal XB","lat":38.76837, "lon":-85.74923,"Firmware Version":"4MR5RCwCA01","IMEI":"865814040895037","ICCID":"89148000006725028573"},
        {"id": "cam_2","name":"Middle Field","make":"Tactacam","model":"Reveal XB","lat":38.76546,"lon":-85.75380,"Firmware Version":"4KR3RCwD403","IMEI":"860322064484733","ICCID":"89148000009166554230"},
        {"id": "cam_3","name":"Big Field Southeast Corner","make":"Tactacam","model":"Reveal XB","lat":38.76714,"lon":-85.75110,"Firmware Version":"4KR3RCwD403","IMEI":"864049054538253","ICCID":"89148000007316377965"},
        {"id": "cam_4","name":"Fence Row","make":"Tactacam","model":"Reveal XB","lat":38.76543,"lon":-85.74962,"Firmware Version":"4KR3RCwD403","IMEI":"864049054760030","ICCID":"89148000007316377957"},
        {"id": "cam_5","name":"Road Between Fields","make":"Tactacam","model":"Reveal X","lat":38.7669,"lon":-85.75194,"Firmware Version":"4MR5RCwCA01","IMEI":"865814040959387","ICCID":"89148000006725030033"},
        {"id": "cam_6","name":"Valley Below Wades Stand","make":"Tactacam","model":"Reveal X","lat":38.76719,"lon":-85.75442,"Firmware Version":"5MR3RCwCA01","IMEI":"865814046557219","ICCID":"89148000006724628969"},
        {"id": "cam_7","name":"Backwoods Road","make":"Tactacam","model":"Reveal XB","lat":38.77045,"lon":-85.75267,"Firmware Version":"4MR5RCwCA01","IMEI":"865814040895069","ICCID":"89148000006725028807"},
        {"id": "cam_8","name":"Big Field West","make":"Tactacam","model":"Reveal XB","lat":38.76968,"lon":-85.75298,"Firmware Version":"4KR3RCwD403","IMEI":"860322064136796","ICCID":"89148000009166036691"},
        {"id": "cam_9","name":"Small Field","make":"Tactacam","model":"Reveal XB","lat":38.77210,"lon":-85.75015,"Firmware Version":"4MR5RCwCA01","IMEI":"865814040895076","ICCID":"89148000006725028915"},
        {"id": "cam_10","name":"Ultra 01","make":"Tactacam","model":"Reveal Ultra","lat":41.45602,"lon":-96.75563,"App Version":"1.5.82.4","MCU Version":"1.1.8.4","Firmware Version":"1.0.20.4","IMEI":"016687000199584", "ICCID": "89148000011670814076"},
        {"id": "cam_11","name":"Ultra 02","make":"Tactacam","model":"Reveal Ultra","lat":41.45753,"lon":-96.75740,"App Version":"1.5.82.4","MCU Version":"1.1.8.4","Firmware Version":"1.0.20.4","IMEI":"016687000229829","ICCID":"89148000011146797095"},
    ]
