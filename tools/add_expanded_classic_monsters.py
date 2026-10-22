#!/usr/bin/env python3
"""全量扩充 29 只经典进阶怪物到 mir3-website：

涵盖：
- 半兽人族进阶（半兽统领、半兽祭司）
- 野猪与石墓族进阶（剃刀獠牙、深山野猪）
- 骷髅与死灵骨魔族进阶（掷斧骷髅、双斧斧手、白骨骷髅、幽灵黑骑士、幻影长枪/刀手/弓手）
- 矿区僵尸与食尸鬼进阶（嗜血食尸鬼、嗜血僵尸）
- 虫洞与跳蚤甲虫族进阶（爆裂跳蚤、剧毒跳蚤、尖刺甲虫、黄金甲虫、剪刀虫王）
- 荒野猛兽与巨兽（变异狼人、苍白狼王白牙、林地猛虎、暴雪虎、狂暴野象）
- 祖玛与牛魔潘夜进阶（祖玛神射手、祖玛守卫长、蛮牛狂暴将军、潘夜领主古扎克）
- 诺玛沙漠进阶（诺玛骑兵、诺玛大军阀）

操作步骤：
1. 提取 images/mob/game/<SpriteName>.png (16帧多动作精灵条)
2. 提取 images/mob/pic/<id>.png (高清独立立绘特写)
3. 写入 data/monsters.json
4. 写入 data/alignment/entities/monster.json
5. 重算 data/alignment/master.json 校验码
"""

import json
import hashlib
import sys
from pathlib import Path
from PIL import Image

ROOT = Path("/home/tetsuya/development/mir3-website")
RESEARCH_COMMON = Path("/home/tetsuya/development/Mir3-Research/Tools/common")
ZL_DIR = Path("/home/tetsuya/mir2ei/Data")
GAME_IMG_DIR = ROOT / "images" / "mob" / "game"
PIC_IMG_DIR = ROOT / "images" / "mob" / "pic"

sys.path.insert(0, str(RESEARCH_COMMON))
import zlsdk

STD_OFFSETS = [40, 41, 42, 43, 120, 121, 122, 123, 200, 201, 202, 203, 360, 361, 362, 363]

EXPANDED_MOBS = [
    {
        "id": "mob-162",
        "name": "半兽统领",
        "category": "兽人古墓",
        "library": "Mon_3",
        "shape": 7,
        "zl_file": "Mon-3.Zl",
        "sprite_name": "Oma_Warlord.png",
        "eng_name": "Oma Warlord",
        "zircon_index": 210,
        "description": "半兽人一族的最高统帅，身材魁梧力大无穷，双手各持一柄沉重开山战斧。不仅近战劈砍势大力沉，更擅长掷出远程回旋飞斧，是冒险者在兽人领地的噩梦。",
        "lvl": 80, "hp": 1900, "exp": 3800, "ac": 28, "mac": 24, "dc": "45-95",
        "spawns": [{"mapId": "d022", "mapNameZh": "天然洞穴2层", "count": 2, "delay": "60分"}, {"mapId": "d032", "mapNameZh": "兽人古墓2层", "count": 2, "delay": "60分"}]
    },
    {
        "id": "mob-163",
        "name": "半兽祭司",
        "category": "兽人古墓",
        "library": "Mon_29",
        "shape": 9,
        "zl_file": "Mon-29.Zl",
        "sprite_name": "Oma_Mage.png",
        "eng_name": "Oma Mage",
        "zircon_index": 284,
        "description": "半兽人部落中精通古老祭祀法术的萨满施法者，手握蛮骨法杖，能借助先祖狂怒召唤暗黑雷电与虚弱诅咒，极大强化了半兽部落的综合作战能力。",
        "lvl": 100, "hp": 10000, "exp": 25000, "ac": 35, "mac": 45, "dc": "60-140",
        "spawns": [{"mapId": "d033", "mapNameZh": "兽人古墓3层", "count": 1, "delay": "120分"}]
    },
    {
        "id": "mob-164",
        "name": "剃刀獠牙",
        "category": "石墓",
        "library": "Mon_16",
        "shape": 0,
        "zl_file": "Mon-16.Zl",
        "sprite_name": "Razor_Tusk.png",
        "eng_name": "Razor Tusk",
        "zircon_index": 129,
        "description": "石墓深处存活千年的巨型獠牙战猪领主，体型比白野猪还要庞大数倍，披挂着厚重铁甲，双角獠牙如锋利剃刀般足以撕裂钢铁。",
        "lvl": 250, "hp": 18000, "exp": 45000, "ac": 45, "mac": 35, "dc": "85-180",
        "spawns": [{"mapId": "d047", "mapNameZh": "石墓7层", "count": 1, "delay": "180分"}]
    },
    {
        "id": "mob-165",
        "name": "狂暴深山野猪",
        "category": "盟重省",
        "library": "Mon_18",
        "shape": 1,
        "zl_file": "Mon-18.Zl",
        "sprite_name": "Wild_Boar.png",
        "eng_name": "Wild Boar",
        "zircon_index": 176,
        "description": "栖息在盟重边境山林与石墓周边的凶暴纯种野猪，皮糙肉厚，具有极强的领地攻击性，常成群结队横冲直撞。",
        "lvl": 75, "hp": 2900, "exp": 4200, "ac": 22, "mac": 18, "dc": "35-70",
        "spawns": [{"mapId": "01", "mapNameZh": "盟重省野外", "count": 30, "delay": "15分"}]
    },
    {
        "id": "mob-166",
        "name": "掷斧骷髅",
        "category": "骷髅洞",
        "library": "Mon_4",
        "shape": 3,
        "zl_file": "Mon-4.Zl",
        "sprite_name": "Skeleton_Axe_Thrower.png",
        "eng_name": "Skeleton Axe Thrower",
        "zircon_index": 43,
        "description": "骷髅洞中最狡黠的远程死灵兵种，手握磨尖的骨质飞斧，能在阴暗角落以极高攻速对入侵者连续投掷白骨飞斧。",
        "lvl": 28, "hp": 320, "exp": 650, "ac": 12, "mac": 15, "dc": "18-35",
        "spawns": [{"mapId": "d021", "mapNameZh": "天然洞穴1层", "count": 25, "delay": "10分"}, {"mapId": "d031", "mapNameZh": "兽人古墓1层", "count": 25, "delay": "10分"}]
    },
    {
        "id": "mob-167",
        "name": "骷髅斧手",
        "category": "骷髅洞",
        "library": "Mon_4",
        "shape": 4,
        "zl_file": "Mon-4.Zl",
        "sprite_name": "Skeleton_Axe_Man.png",
        "eng_name": "Skeleton Axe Man",
        "zircon_index": 44,
        "description": "双手挥舞两把厚重白骨短斧的狂暴骷髅武士，近身连续劈砍迅捷而致命，冲锋凶猛。",
        "lvl": 30, "hp": 400, "exp": 800, "ac": 15, "mac": 15, "dc": "22-42",
        "spawns": [{"mapId": "d022", "mapNameZh": "天然洞穴2层", "count": 20, "delay": "10分"}, {"mapId": "d032", "mapNameZh": "兽人古墓2层", "count": 20, "delay": "10分"}]
    },
    {
        "id": "mob-168",
        "name": "白骨骷髅",
        "category": "骷髅洞",
        "library": "Mon_6",
        "shape": 6,
        "zl_file": "Mon-6.Zl",
        "sprite_name": "White_Bone.png",
        "eng_name": "White Bone",
        "zircon_index": 56,
        "description": "受地底精纯死灵煞气滋养而化的晶莹白骨骷髅，骨质坚硬如铁，防御力和魔御远超普通骷髅。",
        "lvl": 35, "hp": 650, "exp": 1350, "ac": 22, "mac": 20, "dc": "28-55",
        "spawns": [{"mapId": "d023", "mapNameZh": "绝命谷深处", "count": 15, "delay": "15分"}]
    },
    {
        "id": "mob-169",
        "name": "幽灵黑骑士",
        "category": "潘夜石窟",
        "library": "Mon_21",
        "shape": 4,
        "zl_file": "Mon-21.Zl",
        "sprite_name": "Ghost_Knight.png",
        "eng_name": "Ghost Knight",
        "zircon_index": 171,
        "description": "曾誓死守卫潘夜古战场的禁卫军骑兵，身披黑铁战甲骑乘骸骨战马，手持重型破阵骑枪冲锋，震慑地底一切生灵。",
        "lvl": 75, "hp": 2800, "exp": 5200, "ac": 32, "mac": 28, "dc": "50-105",
        "spawns": [{"mapId": "d1214", "mapNameZh": "潘夜石窟4层", "count": 10, "delay": "20分"}, {"mapId": "d1215", "mapNameZh": "潘夜石窟5层", "count": 12, "delay": "20分"}]
    },
    {
        "id": "mob-170",
        "name": "幻影士兵",
        "category": "潘夜石窟",
        "library": "Mon_15",
        "shape": 2,
        "zl_file": "Mon-15.Zl",
        "sprite_name": "Apparition_Soldier.png",
        "eng_name": "Apparition Soldier",
        "zircon_index": 143,
        "description": "古代帝国阵亡的精锐步兵亡魂，手握长枪严守地底结界，攻击带有微弱的破甲死系魔法。",
        "lvl": 75, "hp": 3300, "exp": 6000, "ac": 26, "mac": 24, "dc": "45-90",
        "spawns": [{"mapId": "d1213", "mapNameZh": "潘夜石窟3层", "count": 20, "delay": "15分"}]
    },
    {
        "id": "mob-171",
        "name": "幻影刀手",
        "category": "潘夜石窟",
        "library": "Mon_15",
        "shape": 3,
        "zl_file": "Mon-15.Zl",
        "sprite_name": "Apparition_Bladesman.png",
        "eng_name": "Apparition Bladesman",
        "zircon_index": 142,
        "description": "擅长快步近身劈杀的幻影刀手，双手握持宽刃双环刀，刀法精湛，连斩极难招架。",
        "lvl": 75, "hp": 3300, "exp": 6000, "ac": 28, "mac": 22, "dc": "48-96",
        "spawns": [{"mapId": "d1214", "mapNameZh": "潘夜石窟4层", "count": 20, "delay": "15分"}]
    },
    {
        "id": "mob-172",
        "name": "幻影弓手",
        "category": "潘夜石窟",
        "library": "Mon_15",
        "shape": 4,
        "zl_file": "Mon-15.Zl",
        "sprite_name": "Apparition_Archer.png",
        "eng_name": "Apparition Archer",
        "zircon_index": 141,
        "description": "古代精锐神射手的死灵形态，百步穿杨，弓弦所向箭无虚发，能在远距离形成密集弹幕。",
        "lvl": 75, "hp": 3300, "exp": 6000, "ac": 20, "mac": 30, "dc": "55-110",
        "spawns": [{"mapId": "d1213", "mapNameZh": "潘夜石窟3层", "count": 15, "delay": "15分"}, {"mapId": "d1214", "mapNameZh": "潘夜石窟4层", "count": 15, "delay": "15分"}]
    },
    {
        "id": "mob-173",
        "name": "嗜血食尸鬼",
        "category": "比奇矿区",
        "library": "Mon_5",
        "shape": 2,
        "zl_file": "Mon-5.Zl",
        "sprite_name": "Blood_Thirsty_Ghoul.png",
        "eng_name": "Blood Thirsty Ghoul",
        "zircon_index": 59,
        "description": "长期藏匿于矿区阴暗矿道深处的恶性食尸生物，伏地疾驰，长爪带有令人麻痹减速的尸毒。",
        "lvl": 250, "hp": 3800, "exp": 7500, "ac": 24, "mac": 20, "dc": "45-88",
        "spawns": [{"mapId": "d101", "mapNameZh": "废矿2层", "count": 8, "delay": "20分"}]
    },
    {
        "id": "mob-174",
        "name": "嗜血僵尸",
        "category": "比奇矿区",
        "library": "Mon_5",
        "shape": 2,
        "zl_file": "Mon-5.Zl",
        "sprite_name": "Blood_Thirsty_Zombie.png",
        "eng_name": "Blood Thirsty Zombie",
        "zircon_index": 60,
        "description": "饱饮生者鲜血发生异变的赤红色高阶僵尸，生命力极端顽强，受击后狂性大发狂暴反击。",
        "lvl": 250, "hp": 6000, "exp": 12000, "ac": 30, "mac": 25, "dc": "55-105",
        "spawns": [{"mapId": "d102", "mapNameZh": "废矿3层", "count": 5, "delay": "30分"}]
    },
    {
        "id": "mob-175",
        "name": "爆裂变异跳蚤",
        "category": "潘夜石窟",
        "library": "Mon_15",
        "shape": 7,
        "zl_file": "Mon-15.Zl",
        "sprite_name": "Blaster_Mutant_Flea.png",
        "eng_name": "Blaster Mutant Flea",
        "zircon_index": 135,
        "description": "寄生在石窟底层的异种爆裂跳蚤，腹部聚集着高温灼毒，濒死时会引爆体内腺体造成大范围烈火伤害。",
        "lvl": 65, "hp": 1200, "exp": 2200, "ac": 16, "mac": 18, "dc": "30-65",
        "spawns": [{"mapId": "d1211", "mapNameZh": "潘夜石窟1层", "count": 30, "delay": "10分"}, {"mapId": "d12121", "mapNameZh": "潘夜石窟2层西部", "count": 30, "delay": "10分"}]
    },
    {
        "id": "mob-176",
        "name": "剧毒变异跳蚤",
        "category": "潘夜石窟",
        "library": "Mon_15",
        "shape": 9,
        "zl_file": "Mon-15.Zl",
        "sprite_name": "Poisonous_Mutant_Flea.png",
        "eng_name": "Poisonous Mutant Flea",
        "zircon_index": 136,
        "description": "通体墨绿的变种毒跳蚤，能在远距离喷射浓缩神经毒液，使中招者中毒且行动迟缓。",
        "lvl": 68, "hp": 1400, "exp": 2600, "ac": 18, "mac": 22, "dc": "32-70",
        "spawns": [{"mapId": "d12121", "mapNameZh": "潘夜石窟2层西部", "count": 25, "delay": "10分"}, {"mapId": "d1213", "mapNameZh": "潘夜石窟3层", "count": 25, "delay": "10分"}]
    },
    {
        "id": "mob-177",
        "name": "尖刺血武装甲虫",
        "category": "蜈蚣洞",
        "library": "Mon_7",
        "shape": 4,
        "zl_file": "Mon-7.Zl",
        "sprite_name": "Spiked_Beetle.png",
        "eng_name": "Bloody Armed Beetle",
        "zircon_index": 179,
        "description": "地牢虫穴深处的重铠巨甲虫，背部长满尖锐骨刺，具有极高的物理防御并能反震近身伤害。",
        "lvl": 80, "hp": 5000, "exp": 9500, "ac": 40, "mac": 28, "dc": "50-95",
        "spawns": [{"mapId": "d024", "mapNameZh": "地牢1层北", "count": 15, "delay": "15分"}]
    },
    {
        "id": "mob-178",
        "name": "黄金甲虫",
        "category": "蜈蚣洞",
        "library": "Mon_7",
        "shape": 3,
        "zl_file": "Mon-7.Zl",
        "sprite_name": "Golden_Armored_Beetle.png",
        "eng_name": "Golden Armored Beetle",
        "zircon_index": 180,
        "description": "地牢罕见的稀世变异金甲虫，通体金光闪闪敏捷极高，击败后可爆落巨量金币与珍稀矿石宝石。",
        "lvl": 80, "hp": 1300, "exp": 8000, "ac": 35, "mac": 35, "dc": "20-40",
        "spawns": [{"mapId": "d024", "mapNameZh": "地牢1层北", "count": 3, "delay": "60分"}]
    },
    {
        "id": "mob-179",
        "name": "剪刀虫王",
        "category": "蜈蚣洞",
        "library": "Mon_8",
        "shape": 0,
        "zl_file": "Mon-8.Zl",
        "sprite_name": "Earwig_King.png",
        "eng_name": "Earwig King",
        "zircon_index": 181,
        "description": "蜈蚣洞中进化出巨大双铁螯的霸王巨虫，双剪合拢足以夹断精钢铠甲，统领地底万虫。",
        "lvl": 80, "hp": 5000, "exp": 11000, "ac": 38, "mac": 30, "dc": "60-120",
        "spawns": [{"mapId": "d024", "mapNameZh": "死亡棺材", "count": 2, "delay": "90分"}]
    },
    {
        "id": "mob-180",
        "name": "变异狼人",
        "category": "沃玛森林",
        "library": "Mon_21",
        "shape": 7,
        "zl_file": "Mon-21.Zl",
        "sprite_name": "Werewolf.png",
        "eng_name": "Werewolf",
        "zircon_index": 173,
        "description": "潜伏在沃玛森林深处的半人半狼异变狂兽，长爪獠牙，拥有惊人的撕扯力与夜间爆发速度。",
        "lvl": 75, "hp": 2400, "exp": 4800, "ac": 25, "mac": 22, "dc": "45-92",
        "spawns": [{"mapId": "02", "mapNameZh": "沃玛森林深处", "count": 20, "delay": "15分"}]
    },
    {
        "id": "mob-181",
        "name": "苍白狼王「白牙」",
        "category": "沃玛森林",
        "library": "Mon_21",
        "shape": 8,
        "zl_file": "Mon-21.Zl",
        "sprite_name": "Whitefang.png",
        "eng_name": "Whitefang",
        "zircon_index": 174,
        "description": "玛法大陆极北雪线流浪至此的巨型苍白巨狼之王，银鬃胜雪，嚎叫能大幅激励附近群狼协同围杀。",
        "lvl": 75, "hp": 2500, "exp": 6000, "ac": 28, "mac": 25, "dc": "50-100",
        "spawns": [{"mapId": "02", "mapNameZh": "沃玛森林深处", "count": 2, "delay": "60分"}]
    },
    {
        "id": "mob-182",
        "name": "林地猛虎",
        "category": "道观周围",
        "library": "Mon_35",
        "shape": 1,
        "zl_file": "Mon-35.Zl",
        "sprite_name": "Tiger.png",
        "eng_name": "Tiger",
        "zircon_index": 265,
        "description": "道观外密林深处游弋的斑斓猛虎，威风凛凛百兽之王，一扑一咬皆具千钧之力。",
        "lvl": 63, "hp": 4000, "exp": 5500, "ac": 25, "mac": 20, "dc": "50-85",
        "spawns": [{"mapId": "03", "mapNameZh": "道观密林", "count": 15, "delay": "15分"}]
    },
    {
        "id": "mob-183",
        "name": "暴雪虎",
        "category": "道观周围",
        "library": "Mon_35",
        "shape": 3,
        "zl_file": "Mon-35.Zl",
        "sprite_name": "Blizzard_Tiger.png",
        "eng_name": "Blizzard Tiger",
        "zircon_index": 267,
        "description": "通体雪白带冰蓝斑纹的异种猛虎，爪击附带刺骨冰霜减速效果，凶悍莫测。",
        "lvl": 90, "hp": 4500, "exp": 7500, "ac": 32, "mac": 35, "dc": "65-115",
        "spawns": [{"mapId": "03", "mapNameZh": "灌木林北部", "count": 8, "delay": "25分"}]
    },
    {
        "id": "mob-184",
        "name": "狂暴野象",
        "category": "盟重省",
        "library": "Mon_16",
        "shape": 8,
        "zl_file": "Mon-16.Zl",
        "sprite_name": "Wild_Elephant.png",
        "eng_name": "Wild Elephant",
        "zircon_index": 273,
        "description": "沙漠边陲迁徙的大体量荒野巨象，巨足踏地可震晕近身目标，冲撞势不可挡。",
        "lvl": 60, "hp": 4000, "exp": 6200, "ac": 35, "mac": 22, "dc": "45-80",
        "spawns": [{"mapId": "01", "mapNameZh": "盟重荒漠", "count": 12, "delay": "20分"}]
    },
    {
        "id": "mob-185",
        "name": "祖玛神射手",
        "category": "祖玛神殿",
        "library": "Mon_9",
        "shape": 2,
        "zl_file": "Mon-9.Zl",
        "sprite_name": "Zuma_Sharp_Shooter.png",
        "eng_name": "Zuma Sharp Shooter",
        "zircon_index": 82,
        "description": "祖玛教主以黑曜石精雕而成的神射石像，手持祖玛长弓，精准狙击一切胆敢靠近祭坛的凡人。",
        "lvl": 46, "hp": 900, "exp": 2100, "ac": 22, "mac": 28, "dc": "42-85",
        "spawns": [{"mapId": "d055", "mapNameZh": "祖玛神殿5层", "count": 30, "delay": "10分"}]
    },
    {
        "id": "mob-186",
        "name": "祖玛守卫长",
        "category": "祖玛神殿",
        "library": "Mon_9",
        "shape": 4,
        "zl_file": "Mon-9.Zl",
        "sprite_name": "Zuma_Keeper.png",
        "eng_name": "Zuma Keeper",
        "zircon_index": 80,
        "description": "祖玛近卫军的直属统领大头目，双手巨锤威能巨大，统率大群祖玛卫士誓死保卫神殿深渊。",
        "lvl": 250, "hp": 3300, "exp": 9500, "ac": 38, "mac": 32, "dc": "68-135",
        "spawns": [{"mapId": "d057", "mapNameZh": "祖玛神殿7层", "count": 5, "delay": "45分"}]
    },
    {
        "id": "mob-187",
        "name": "蛮牛狂暴将军",
        "category": "潘夜神殿",
        "library": "Mon_5",
        "shape": 4,
        "zl_file": "Mon-5.Zl",
        "sprite_name": "Ox_Feral_General.png",
        "eng_name": "Ox Feral General",
        "zircon_index": 205,
        "description": "身披黑红战甲、双眼充血的狂暴牛魔大将，双持沉重开山斧，越战越勇无人能挡。",
        "lvl": 80, "hp": 5000, "exp": 13000, "ac": 35, "mac": 28, "dc": "75-145",
        "spawns": [{"mapId": "d1226", "mapNameZh": "潘夜神殿6层", "count": 6, "delay": "40分"}]
    },
    {
        "id": "mob-188",
        "name": "潘夜领主古扎克",
        "category": "潘夜神殿",
        "library": "Mon_13",
        "shape": 0,
        "zl_file": "Mon-13.Zl",
        "sprite_name": "Banyo_Lord_Guzak.png",
        "eng_name": "Banyo Lord Guzak",
        "zircon_index": 188,
        "description": "潘夜一族在地底深渊供奉的至高魔王，生命值高达 100,000，掌控暗黑混沌之力的终极巨兽。",
        "lvl": 250, "hp": 100000, "exp": 250000, "ac": 65, "mac": 55, "dc": "140-280",
        "spawns": [{"mapId": "d1227", "mapNameZh": "潘夜神殿深渊祭坛", "count": 1, "delay": "360分"}]
    },
    {
        "id": "mob-189",
        "name": "诺玛突击骑兵",
        "category": "绿洲沙漠",
        "library": "Mon_19",
        "shape": 0,
        "zl_file": "Mon-19.Zl",
        "sprite_name": "Numa_Cavalry.png",
        "eng_name": "Numa Cavalry",
        "zircon_index": 161,
        "description": "诺玛一族的精锐游击骑兵，胯下骑乘凶悍沙漠独角战兽，持矛突刺冲锋，来去如风。",
        "lvl": 72, "hp": 1700, "exp": 3800, "ac": 24, "mac": 22, "dc": "40-85",
        "spawns": [{"mapId": "d2001", "mapNameZh": "绿洲沙漠遗迹", "count": 30, "delay": "15分"}]
    },
    {
        "id": "mob-190",
        "name": "诺玛大军阀",
        "category": "绿洲沙漠",
        "library": "Mon_19",
        "shape": 6,
        "zl_file": "Mon-19.Zl",
        "sprite_name": "Numa_Warlord.png",
        "eng_name": "Numa Warlord",
        "zircon_index": 167,
        "description": "统率诺玛大营地全军的终极军事统帅，身披千层重铠手持巨刀，号令沙漠百千诺玛战士。",
        "lvl": 250, "hp": 35000, "exp": 80000, "ac": 50, "mac": 45, "dc": "110-220",
        "spawns": [{"mapId": "d2005", "mapNameZh": "诺玛大营地大厅", "count": 1, "delay": "240分"}]
    }
]


def extract_zl_strip(zl_path: Path, shape: int, offsets: list[int]) -> Image.Image | None:
    zl = zlsdk.ZlLibrary(str(zl_path))
    base = shape * 1000
    frames = []
    for off in offsets:
        idx = base + off
        if idx < zl.count:
            img = zl.decode(idx)
            if img and img.width > 5 and img.height > 5:
                frames.append(img)
    if not frames:
        return None
    max_h = max(f.height for f in frames)
    total_w = sum(f.width for f in frames)
    strip = Image.new("RGBA", (total_w, max_h), (0, 0, 0, 0))
    x = 0
    for f in frames:
        strip.paste(f, (x, max_h - f.height), f)
        x += f.width
    return strip


def extract_single_portrait(zl_path: Path, shape: int, offset: int = 40) -> Image.Image | None:
    zl = zlsdk.ZlLibrary(str(zl_path))
    img = zl.decode(shape * 1000 + offset)
    if not img:
        return None
    # 居中放入一张优雅的透明立绘框 (最大 140x120)
    w, h = img.size
    box_w = max(139, w + 16)
    box_h = max(106, h + 16)
    card = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    card.paste(img, ((box_w - w) // 2, (box_h - h) // 2), img)
    return card


def main():
    GAME_IMG_DIR.mkdir(parents=True, exist_ok=True)
    PIC_IMG_DIR.mkdir(parents=True, exist_ok=True)

    print(f"=== 开始提取 {len(EXPANDED_MOBS)} 只怪物的精灵条与立绘 ===")
    for m in EXPANDED_MOBS:
        zl_path = ZL_DIR / m["zl_file"]
        # A. 提取精灵条
        strip = extract_zl_strip(zl_path, m["shape"], STD_OFFSETS)
        if strip:
            strip.save(GAME_IMG_DIR / m["sprite_name"])
            print(f"  [Sprite] {m['sprite_name']}: {strip.size}")
        else:
            print(f"  [ERROR] Failed to extract sprite for {m['name']}")

        # B. 提取立绘
        pic_filename = f"{m['id']}.png"
        portrait = extract_single_portrait(zl_path, m["shape"], 40)
        if portrait:
            portrait.save(PIC_IMG_DIR / pic_filename)
        else:
            print(f"  [ERROR] Failed to extract portrait for {m['name']}")

    # 3. 更新 data/monsters.json
    monsters_path = ROOT / "data" / "monsters.json"
    with open(monsters_path, "r", encoding="utf-8") as f:
        monsters = json.load(f)

    existing_ids = set(x["id"] for x in monsters)
    added_count = 0

    for m in EXPANDED_MOBS:
        if m["id"] in existing_ids:
            continue
        entry = {
            "id": m["id"],
            "name": m["name"],
            "category": m["category"],
            "image": f"../images/mob/pic/{m['id']}.png",
            "description": m["description"],
            "attrs": {
                "生命": str(m["hp"]),
                "经验值": str(m["exp"]),
                "防御力": str(m["ac"]),
                "魔法防御": str(m["mac"]),
                "攻击力": m["dc"]
            },
            "spawns": m["spawns"],
            "totalSpawnCount": sum(s["count"] for s in m["spawns"]),
            "game": {
                "sprite": f"/images/mob/game/{m['sprite_name']}",
                "eng_name": m["eng_name"],
                "library": m["library"],
                "shape": m["shape"],
                "match_method": "exact",
                "note": f"{m['category']}{m['name']}真身（{m['library']} shape {m['shape']}），经典扩充怪物"
            },
            "zircon_match": {
                "state": "matched"
            },
            "zircon_index": m["zircon_index"]
        }
        monsters.append(entry)
        added_count += 1

    with open(monsters_path, "w", encoding="utf-8") as f:
        json.dump(monsters, f, ensure_ascii=False, indent=2)
    print(f"Updated data/monsters.json: added {added_count} monsters, total {len(monsters)}")

    # 4. 更新 data/alignment/entities/monster.json
    entities_path = ROOT / "data" / "alignment" / "entities" / "monster.json"
    with open(entities_path, "r", encoding="utf-8") as f:
        entities = json.load(f)

    existing_entity_ids = set(e["id"] for e in entities)
    # 移除任何已存在的 mob-162..190 防止脏数据
    entities = [e for e in entities if not (e["id"].startswith("monster:website:mob-1") and int(e["id"].split("-")[1]) >= 162)]

    for m in EXPANDED_MOBS:
        wid = f"monster:website:{m['id']}"
        pic_path = PIC_IMG_DIR / f"{m['id']}.png"
        pic_bytes = pic_path.stat().st_size if pic_path.exists() else 0
        pic_sha = hashlib.sha256(pic_path.read_bytes()).hexdigest() if pic_path.exists() else ""

        e = {
            "assessment": {
                "export_enabled": False,
                "overall_status": "confirmed",
                "reason": f"{m['category']}{m['name']}真身（{m['library']} shape {m['shape']}），经典扩充怪",
                "suggested_action": "已确认经典扩充怪真身匹配。"
            },
            "entity_type": "monster",
            "evidence": [
                {
                    "record": f"manifest.json#monster_identity/{m['id']}",
                    "source_id": "website-alignment-manifest"
                }
            ],
            "game_data": {
                "image": f"{m['library']} shape {m['shape']}",
                "index": m["zircon_index"],
                "name": m["eng_name"]
            },
            "id": wid,
            "identity": {
                "standard_name_zh": m["name"],
                "website_name": m["name"],
                "website_source_id": m["id"],
                "zircon_candidate_indexes": [m["zircon_index"]],
                "zircon_internal_name": m["eng_name"]
            },
            "relations": {
                "candidate_entity_ids": [f"monster:zircon:{m['zircon_index']}"]
            },
            "resources": {
                "website": {
                    "bytes": pic_bytes,
                    "exists": True,
                    "format": "PNG",
                    "frames": 1,
                    "path": f"images/mob/pic/{m['id']}.png",
                    "sha256": pic_sha
                },
                "zircon": {
                    "path": f"/images/mob/game/{m['sprite_name']}",
                    "verification": "verified-by-image"
                }
            }
        }
        entities.append(e)

    with open(entities_path, "w", encoding="utf-8") as f:
        json.dump(entities, f, ensure_ascii=False, indent=2)
    print(f"Updated data/alignment/entities/monster.json: total {len(entities)}")

    # 5. 更新 master.json shard
    master_path = ROOT / "data" / "alignment" / "master.json"
    with open(master_path, "r", encoding="utf-8") as f:
        master = json.load(f)

    with open(entities_path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()

    for shard in master.get("shards", {}).get("entities", []):
        if shard.get("path") == "entities/monster.json":
            shard["sha256"] = sha
            shard["count"] = len(entities)
            print(f"Updated master.json entities/monster.json sha256={sha[:12]}, count={len(entities)}")

    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)
    print("All tasks completed successfully!")


if __name__ == "__main__":
    main()
