main.floors.MT12=
{
    "floorId": "MT12",
    "title": "第 12 层",
    "name": "第 12 层",
    "width": 13,
    "height": 13,
    "canFlyTo": true,
    "canUseQuickShop": true,
    "cannotViewMap": false,
    "images": [],
    "ratio": 1,
    "defaultGround": "ground",
    "firstArrive": [],
    "eachArrive": [],
    "parallelDo": "",
    "events": {
        "1,1": [
            {
                "type": "openShop",
                "id": "keyShop2",
                "open": true
            }
        ],
        "11,1": {
            "trigger": "action",
            "enable": true,
            "noPass": null,
            "displayDamage": true,
            "opacity": 1,
            "filter": {
                "blur": 0,
                "hue": 0,
                "grayscale": 0,
                "invert": false,
                "shadow": 0
            },
            "data": [
                {
                    "type": "playSound",
                    "name": "constants.mp3"
                },
                {
                    "type": "function",
                    "function": "function(){\ncore.addItem('icePickaxe',1)\n}"
                },
                {
                    "type": "setText",
                    "align": "center"
                },
                "\t[星光神锒]把它交给第四层的小偷，小偷便会用它打开第十八层的隐藏地面（你就可以救出公主了）。",
                {
                    "type": "setText",
                    "align": "left"
                },
                {
                    "type": "hide",
                    "remove": true
                }
            ]
        }
    },
    "changeFloor": {
        "1,11": {
            "floorId": ":next",
            "stair": "downFloor"
        },
        "11,11": {
            "floorId": ":before",
            "stair": "upFloor"
        }
    },
    "afterBattle": {},
    "afterGetItem": {},
    "afterOpenDoor": {},
    "cannotMove": {},
    "map": [
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3],
    [  3,122, 28,  1,  0,226,227,226,  0,  1, 32, 48,  3],
    [  3, 27,  0,  1,  0,  1, 81,  1,  0,  1,  0, 32,  3],
    [  3,  0,  0,  1,  0,  1,227,  1,  0,  1,  0,  0,  3],
    [  3,  0,224,  1,  0,  1, 21,  1,  0,  1,228,  0,  3],
    [  3,224,225,  1,  0,  1, 21,  1,  0,  1,247,228,  3],
    [  3,  1, 82,  1,  0,  1, 31,  1,  0,  1, 82,  1,  3],
    [  3,  0,  0,  0,  0,  1, 31,  1,  0,  0,  0,  0,  3],
    [  3,  1,  1,  1,  0,  1,  1,  1,  0,  1,  1,  1,  3],
    [  3, 28,224, 81,222,222,223,222,222, 81,224, 27,  3],
    [  3,  1,  1,  1,  1,  1, 82,  1,  1,  1,  1,  1,  3],
    [  3, 87,  0,  0,  0,  0,  0,  0,  0,  0,  0, 88,  3],
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3]
],
    "bgmap": [

],
    "fgmap": [

],
    "upFloor": [
        2,
        11
    ],
    "downFloor": [
        10,
        11
    ],
    "bgm": "area2.mp3",
    "beforeBattle": {},
    "cannotMoveIn": {},
    "autoEvent": {},
    "canFlyFrom": true
}