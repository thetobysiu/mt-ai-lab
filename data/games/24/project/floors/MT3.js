main.floors.MT3=
{
    "floorId": "MT3",
    "title": "第 3 层",
    "name": "第 3 层",
    "width": 13,
    "height": 13,
    "canFlyTo": true,
    "canUseQuickShop": true,
    "cannotViewMap": false,
    "images": [],
    "item_ratio": 1,
    "defaultGround": "ground",
    "firstArrive": [],
    "eachArrive": [],
    "parallelDo": "",
    "events": {
        "6,1": [
            {
                "type": "openShop",
                "id": "moneyShop1",
                "open": true
            }
        ]
    },
    "changeFloor": {
        "1,11": {
            "floorId": ":before",
            "stair": "upFloor"
        },
        "11,11": {
            "floorId": ":next",
            "stair": "downFloor"
        }
    },
    "afterBattle": {},
    "afterGetItem": {},
    "afterOpenDoor": {},
    "cannotMove": {},
    "map": [
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3],
    [  3, 35,202, 21,  1,  7,131,  8,  1,  1,  1,  1,  3],
    [  3,202, 21,  0,  1,  0,  0,  0,  1,  0,205,  0,  3],
    [  3, 21,209,  0,  1,  1, 81,  1,  1,  0,  1,  0,  3],
    [  3,  1, 81,  1,  1,  0,209,  0,  1, 21,  1,202,  3],
    [  3,  0,  0,  0,  1,  1,  1,  0,  1, 21,  1,205,  3],
    [  3,201,  1,  0,205,202,205,  0,  1, 21,  1,202,  3],
    [  3,201,  1,  1,  1,  1,  1,  0,  0,  0,  1,  0,  3],
    [  3,  0,  0,  0,  0,  0,  1,  1, 81,  1,  1,  0,  3],
    [  3,  1,  1,  1,  1,205,  1,202,  0,202,  1,  0,  3],
    [  3,  1,  0,  0,  0,  0,  1, 27,205, 21,  1,  0,  3],
    [  3, 88,  0,  1,  1,  1,  1, 28, 32, 21,  1, 87,  3],
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3]
],
    "bgmap": [

],
    "fgmap": [

],
    "upFloor": [
        11,
        10
    ],
    "downFloor": [
        2,
        11
    ],
    "bgm": "area1.mp3",
    "beforeBattle": {},
    "cannotMoveIn": {},
    "autoEvent": {},
    "canFlyFrom": true
}