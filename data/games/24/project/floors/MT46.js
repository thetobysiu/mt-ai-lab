main.floors.MT46=
{
    "floorId": "MT46",
    "title": "魔塔 第46层",
    "name": "第 46 层",
    "width": 13,
    "height": 13,
    "map": [
    [  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1],
    [  1,  0,220, 81,  0,  7,131,  8,  0, 82,  0, 88,  1],
    [  1, 31,  0,  1,  0,  0,  0,  0,  0,  1,  0,  0,  1],
    [  1, 27,  0,  1,  1,  1,  1,  1,  1,  1,  1, 81,  1],
    [  1,  0,219, 81,  0,  0,  0,  0,  0,207,  0,  0,  1],
    [  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1, 81,  1],
    [  1,225,  0,224,  0,227,  1, 31,  0, 81,204,  0,  1],
    [  1,  0,  1,  1,  1,  0,  1,  0,220,  1,  0,  0,  1],
    [  1,213,  1, 26,  1,204,  1, 81,  1,  1,  1, 81,  1],
    [  1,  0,  1,  0,219,  0,  1,  0,121,  1,219,  0,  1],
    [  1,206,  1,  1,  1,  1,  1,  0,  0,  1,  0,  0,  1],
    [  1,  0,209,  0,202,  0, 82,  0,  0, 81,  0, 87,  1],
    [  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1,  1]
],
    "canFlyTo": true,
    "canFlyFrom": true,
    "canUseQuickShop": true,
    "images": [],
    "ratio": 5,
    "defaultGround": "ground",
    "bgm": "section5.mp3",
    "firstArrive": [],
    "eachArrive": [],
    "parallelDo": "",
    "events": {
        "6,1": [
            {
                "type": "setValue",
                "name": "flag:ratio",
                "value": "core.status.maps[core.status.floorId].ratio"
            },
            {
                "type": "while",
                "condition": "true",
                "data": [
                    {
                        "type": "choices",
                        "text": "\t[祭坛,blueShop]想要增加你的能力吗？\n如果你有100个金币，你可以任意选择一项：",
                        "choices": [
                            {
                                "text": "生命+4000",
                                "action": [
                                    {
                                        "type": "if",
                                        "condition": "(status:money>=100)",
                                        "true": [
                                            {
                                                "type": "playSound",
                                                "name": "获得道具"
                                            },
                                            {
                                                "type": "setValue",
                                                "name": "status:hp",
                                                "operator": "+=",
                                                "value": "4000"
                                            },
                                            {
                                                "type": "setValue",
                                                "name": "status:money",
                                                "operator": "-=",
                                                "value": "100"
                                            },
                                            {
                                                "type": "setValue",
                                                "name": "flag:times1",
                                                "operator": "+=",
                                                "value": "1"
                                            },
                                            {
                                                "type": "function",
                                                "function": "function(){\ncore.addFlag(`${core.getFlag('ratio')}区购买hp`, 4000);\ncore.addFlag(`${core.getFlag('ratio')}区购买hp次数`, 1);\n}"
                                            }
                                        ],
                                        "false": [
                                            {
                                                "type": "tip",
                                                "text": "你的金币不足100枚，无法供奉！"
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                "text": "攻击+20",
                                "action": [
                                    {
                                        "type": "if",
                                        "condition": "(status:money>=100)",
                                        "true": [
                                            {
                                                "type": "playSound",
                                                "name": "获得道具"
                                            },
                                            {
                                                "type": "setValue",
                                                "name": "status:atk",
                                                "operator": "+=",
                                                "value": "20"
                                            },
                                            {
                                                "type": "setValue",
                                                "name": "status:money",
                                                "operator": "-=",
                                                "value": "100"
                                            },
                                            {
                                                "type": "setValue",
                                                "name": "flag:times1",
                                                "operator": "+=",
                                                "value": "1"
                                            },
                                            {
                                                "type": "function",
                                                "function": "function(){\ncore.addFlag(`${core.getFlag('ratio')}区购买atk`, 20);\ncore.addFlag(`${core.getFlag('ratio')}区购买atk次数`, 1);\n}"
                                            }
                                        ],
                                        "false": [
                                            {
                                                "type": "tip",
                                                "text": "你的金币不足100枚，无法供奉！"
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                "text": "防御+20",
                                "action": [
                                    {
                                        "type": "if",
                                        "condition": "(status:money>=100)",
                                        "true": [
                                            {
                                                "type": "playSound",
                                                "name": "获得道具"
                                            },
                                            {
                                                "type": "setValue",
                                                "name": "status:def",
                                                "operator": "+=",
                                                "value": "20"
                                            },
                                            {
                                                "type": "setValue",
                                                "name": "status:money",
                                                "operator": "-=",
                                                "value": "100"
                                            },
                                            {
                                                "type": "setValue",
                                                "name": "flag:times1",
                                                "operator": "+=",
                                                "value": "1"
                                            },
                                            {
                                                "type": "function",
                                                "function": "function(){\ncore.addFlag(`${core.getFlag('ratio')}区购买def`, 20);\ncore.addFlag(`${core.getFlag('ratio')}区购买def次数`, 1);\n}"
                                            }
                                        ],
                                        "false": [
                                            {
                                                "type": "tip",
                                                "text": "你的金币不足100枚，无法供奉！"
                                            }
                                        ]
                                    }
                                ]
                            },
                            {
                                "text": "离开",
                                "action": [
                                    {
                                        "type": "break",
                                        "n": 1
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    },
    "changeFloor": {
        "11,11": {
            "floorId": ":next",
            "stair": "downFloor",
            "time": 0
        },
        "11,1": {
            "floorId": ":before",
            "stair": "upFloor",
            "time": 0
        }
    },
    "afterBattle": {},
    "afterGetItem": {},
    "afterOpenDoor": {},
    "cannotMove": {},
    "fgmap": [

],
    "bgmap": [
    [ 17, 17, 17, 17, 17, 17, 17, 17, 17, 17, 17, 17, 17],
    [ 17,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 17],
    [ 17,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 17],
    [ 17,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 17],
    [ 17,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 17],
    [ 17,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 17],
    [ 17,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 17],
    [ 17,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 17],
    [ 17,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 17],
    [ 17,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 17],
    [ 17,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 17],
    [ 17,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 17],
    [ 17, 17, 17, 17, 17, 17, 17, 17, 17, 17, 17, 17, 17]
],
    "upFloor": [
        11,
        10
    ],
    "downFloor": [
        11,
        2
    ],
    "autoEvent": {},
    "beforeBattle": {},
    "cannotMoveIn": {}
}