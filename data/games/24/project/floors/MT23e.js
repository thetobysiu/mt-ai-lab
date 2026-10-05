main.floors.MT23e=
{
    "floorId": "MT23e",
    "title": "第 23 层",
    "name": "第 23 层",
    "width": 13,
    "height": 13,
    "canFlyTo": false,
    "canUseQuickShop": true,
    "cannotViewMap": false,
    "images": [],
    "ratio": 1,
    "defaultGround": "ground",
    "bgm": "startText.mp3",
    "firstArrive": [],
    "eachArrive": [
        {
            "type": "pauseBgm"
        },
        {
            "type": "resumeBgm"
        }
    ],
    "parallelDo": "",
    "events": {},
    "changeFloor": {
        "1,6": {
            "floorId": "MT22",
            "stair": "upFloor"
        }
    },
    "afterBattle": {},
    "afterGetItem": {},
    "afterOpenDoor": {},
    "cannotMove": {},
    "map": [
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3],
    [  3, 32,  0,  4,  0,  0,  0, 28, 28, 28,  0,228,  3],
    [  3,  4,  0, 82,  0,  4,  4,  4,  4,  4,  4,  0,  3],
    [  3,  4,  0,  4,  0,228,228,228,247,  4,  4, 28,  3],
    [  3,  4,  0,  4,  4,  4,  4,  4, 50,  4,  4, 28,  3],
    [  3,  4,  0, 63,  4,  4,  4,  4,  4,  4,247,  0,  3],
    [  3, 88,  0, 82, 63,  4,  4, 73,  6,208, 83,  4,  3],
    [  3,  4,  0, 63,  4,  4,  4,  4,  4,  4,247,  0,  3],
    [  3,  4,  0,  4,  4,  4,  4,  4, 50,  4,  4, 28,  3],
    [  3,  4,  0,  4,  0,228,228,228,247,  4,  4, 28,  3],
    [  3,  4,  0, 82,  0,  4,  4,  4,  4,  4,  4,  0,  3],
    [  3, 32,  0,  4,  0,  0,  0, 28, 28, 28,  0,228,  3],
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3]
],
    "bgmap": [

],
    "fgmap": [

],
    "downFloor": [
        2,
        6
    ],
    "upFloor": [
        2,
        6
    ],
    "beforeBattle": {},
    "cannotMoveIn": {},
    "autoEvent": {},
    "canFlyFrom": true,
    "flyPoint": [
        2,
        6
    ]
}