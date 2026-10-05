main.floors.MT7=
{
    "floorId": "MT7",
    "title": "第 7 层",
    "name": "第 7 层",
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
        "6,5": {
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
                    "function": "function(){\ncore.addItem('cross',1)\n}"
                },
                {
                    "type": "setText",
                    "align": "center"
                },
                "\t[幸运十字架]把它交给序章中的仙子，可以将自身的所有能力提升三分之一（攻击、防御和生命值）。",
                {
                    "type": "setText",
                    "align": "left"
                },
                {
                    "type": "setBlock",
                    "number": "1",
                    "loc": [
                        [
                            5,
                            5
                        ]
                    ],
                    "floorId": "MT16"
                },
                {
                    "type": "hide",
                    "remove": true
                }
            ]
        }
    },
    "changeFloor": {
        "5,11": {
            "floorId": ":before",
            "stair": "upFloor"
        },
        "1,1": {
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
    [  3, 87,  0,  0,  0,  0,  0,  0,  0,  1,  1,  1,  3],
    [  3,  1,  1,  0,207,  1, 82,  1,211,  0,  1,  1,  3],
    [  3,  1,  0,207, 28,  1,246,  1, 27,211,  0,  1,  3],
    [  3,  0,  0,  1,  1,  1, 86,  1,  1,  1,  0,  0,  3],
    [  3,  0,  0, 82,246,  6, 55, 86,246, 82,  0,  0,  3],
    [  3,  0,  1,  1,  1,  1, 86,  1,  1,  1,  1,  0,  3],
    [  3,  0,  1, 31, 27,  1,246,  1, 28, 31,  1,  0,  3],
    [  3,  0,  1, 21, 31,  1, 82,  1, 31, 21,  1,  0,  3],
    [  3,  0,  1,  1, 22, 22, 32, 22, 22,  1,  1,  0,  3],
    [  3,  0,  0,  1,  1,  1, 83,  1,  1,  1,  0,  0,  3],
    [  3,  1,  0,  0, 81, 88,  0,  0, 81,  0,  0,  1,  3],
    [  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3,  3]
],
    "bgm": "area1.mp3",
    "bgmap": [

],
    "fgmap": [

],
    "upFloor": [
        2,
        1
    ],
    "downFloor": [
        6,
        11
    ],
    "beforeBattle": {},
    "cannotMoveIn": {},
    "autoEvent": {},
    "canFlyFrom": true
}