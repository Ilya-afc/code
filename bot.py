import asyncio, os, json, random, time, hashlib, re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiohttp import web, ClientSession, TCPConnector
from telethon import TelegramClient
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, PreCheckoutQueryHandler, MessageHandler, filters
from telegram.constants import ParseMode
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice

load_dotenv()
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN", "")
OWNER_ID = 6288011144
OWNER_LINK = "https://t.me/faluoo"

FOUND_FILE = "found_v3.json"
WATCH_FILE = "watch_v3.json"
SUBS_FILE = "subs.json"
REF_FILE = "referrals.json"

BATCH_SIZE = 20  # Увеличили батч для скорости
MIN_DELAY = 0.3  # Меньшая пауза
MAX_DELAY = 0.8  # Меньшая пауза
HTTP_TIMEOUT = 1.5  # Быстрее таймаут
CACHE_TTL = 600  # Больше кэш время
FREE_BATCH = 5
NAME_LENGTH = 7

# Красивые паттерны для фильтрации
BEAUTIFUL_PATTERNS = [
    r'^([a-z])\1{6}$',           # aaaaaaa
    r'^([a-z]{2})\1{2}[a-z]$',   # abababa  
    r'^([a-z]{3})\1[a-z]$',      # abcabca
    r'^[aeiouy]{7}$',            # aeioyua (гласные)
    r'^[bcdfghjklmnpqrstvwxyz]{7}$', # согласные
    r'^([a-z])[aeiou]([a-z])[aeiou]([a-z])[aeiou][a-z]$', # CVCCVCV
    r'^[a-z]+ing$|[a-z]+ed$|[a-z]+er$|[a-z]+or$',         # слова с суффиксами
    r'^(love|like|best|cool|nice|good|great|super|mega|ultra)', # популярные корни
    r'.*(tech|code|dev|app|web|net|sys|api).*',           # технические
    r'.*(game|play|win|fun|joy|fun|fun).*',               # игровые
    r'.*(money|cash|coin|gold|rich|wealth).*',            # финансовые
    r'.*(star|moon|sun|sky|fire|water|earth).*',          # природные
    r'.*(crypto|block|chain|token|nft|dao).*',            # крипто
    r'.*(ai|ml|dl|nn|cv|nlp).*',                          # AI/ML
    r'.*(shop|store|market|trade|deal|sale).*',           # торговые
    r'.*(news|info|data|stat|fact|truth).*',              # информационные
    r'.*(vip|pro|max|top|elite|premium).*',               # премиум
    r'.*(fast|quick|rapid|swift|speed).*',                # скорость
    r'.*(smart|intelli|wise|clever|genius).*',            # интеллект
    r'.*(power|force|energy|vital|core).*',               # сила
    r'.*(magic|mystic|spell|charm|aura).*',               # магия
    r'.*(dream|wish|hope|faith|trust).*',                 # мечты
    r'.*(time|date|clock|hour|min|sec).*',                # время
    r'.*(world|land|zone|area|place|spot).*',             # места
    r'.*(team|crew|gang|squad|unit|group).*',             # группы
    r'.*(king|queen|lord|lady|boss|chief).*',             # титулы
    r'.*(hero|legend|myth|epic|saga|tale).*',             # легенды
    r'.*(wolf|lion|tiger|bear|eagle|hawk).*',             # животные
    r'.*(dragon|phoenix|unicorn|griffin|kraken).*',       # мифические
    r'.*(blade|sword|shield|armor|helm|mail).*',          # оружие
    r'.*(rock|stone|metal|iron|steel|gold).*',            # материалы
    r'.*(wave|flow|stream|river|lake|sea).*',             # вода
    r'.*(wind|air|gas|steam|cloud|mist).*',               # воздух
    r'.*(light|shine|glow|spark|flash|beam).*',           # свет
    r'.*(dark|shadow|night|black|void|null).*',           # тьма
    r'.*(red|blue|green|yellow|purple|orange).*',         # цвета
    r'.*(hot|cold|warm|cool|free|zero).*',                # температура
    r'.*(big|small|long|short|wide|thin).*',              # размеры
    r'.*(new|old|first|last|next|prev).*',                # порядок
    r'.*(one|two|three|four|five|six).*',                 # числа словами
    r'.*(alpha|beta|gamma|delta|omega|sigma).*',          # греческие буквы
    r'.*(prime|main|core|base|root|seed).*',              # основные
    r'.*(node|edge|link|path|route|way).*',               # сети
    r'.*(bit|byte|word|char|line|page).*',                # данные
    r'.*(run|exec|call|func|proc|task).*',                # программирование
    r'.*(test|debug|trace|log|dump|snap).*',              # отладка
    r'.*(build|make|create|form|shape|cast).*',           # создание
    r'.*(break|crash|fail|error|bug|fix).*',              # ошибки
    r'.*(start|stop|pause|resume|abort|kill).*',          # управление
    r'.*(open|close|lock|unlock|auth|perm).*',            # доступ
    r'.*(read|write|save|load|sync|flush).*',             # операции
    r'.*(send|recv|push|pull|emit|listen).*',             # сеть
    r'.*(hash|crypt|encrypt|decrypt|sign|verify).*',      # безопасность
    r'.*(scan|probe|sniff|spy|watch|monitor).*',          # наблюдение
    r'.*(hack|exploit|attack|defend|secure|protect).*',   # взлом
    r'.*(mine|dig|drill|extract|harvest|farm).*',         # добыча
    r'.*(train|learn|teach|study|research|explore).*',    # обучение
    r'.*(grow|develop|evolve|adapt|mutate|transform).*',  # развитие
    r'.*(fight|battle|war|conflict|clash|duel).*',        # борьба
    r'.*(hunt|chase|track|follow|pursue|catch).*',        # охота
    r'.*(escape|flee|hide|seek|find|discover).*',         # поиск
    r'.*(solve|resolve|answer|question|query|search).*',  # вопросы
    r'.*(think|brain|mind|logic|reason|sense).*',         # мышление
    r'.*(feel|emotion|sentiment|mood|spirit|soul).*',     # чувства
    r'.*(art|design|style|trend|mode|fashion).*',         # искусство
    r'.*(music|sound|audio|voice|tone|beat).*',           # музыка
    r'.*(video|film|movie|clip|scene|shot).*',            # видео
    r'.*(photo|image|pic|graph|chart|plot).*',            # изображения
    r'.*(text|word|letter|symbol|mark|sign).*',           # текст
    r'.*(number|digit|count|sum|total|value).*',          # числа
    r'.*(math|calc|compute|formula|equation|function).*', # математика
    r'.*(science|physics|chemistry|biology|geology).*',   # наука
    r'.*(history|past|future|present|moment|era).*',      # время
    r'.*(space|universe|galaxy|planet|star|cosmos).*',    # космос
    r'.*(nature|animal|plant|tree|flower|grass).*',       # природа
    r'.*(human|person|people|man|woman|child).*',         # люди
    r'.*(social|community|network|friend|partner).*',     # общество
    r'.*(business|company|corp|brand|market|trade).*',    # бизнес
    r'.*(finance|bank|invest|stock|bond|fund).*',         # финансы
    r'.*(legal|law|rule|policy|regulation|compliance).*', # право
    r'.*(medical|health|care|treatment|therapy|diagnose).*', # медицина
    r'.*(education|school|college|university|course).*',  # образование
    r'.*(travel|tour|trip|journey|adventure|expedition).*', # путешествия
    r'.*(food|drink|meal|dish|recipe|cuisine).*',         # еда
    r'.*(sport|fitness|exercise|workout|training|competition).*', # спорт
    r'.*(entertainment|media|press|journal|magazine).*',  # развлечения
    r'.*(technology|digital|virtual|cyber|robot|android).*', # технологии
    r'.*(internet|web|online|remote|mobile|wireless).*',  # интернет
    r'.*(software|hardware|firmware|middleware|system).*', # софт/железо
    r'.*(database|storage|cache|buffer|queue|stack).*',   # хранилища
    r'.*(server|client|browser|engine|kernel|driver).*',  # системы
    r'.*(protocol|standard|format|encoding|compression).*', # протоколы
    r'.*(algorithm|structure|pattern|template|framework).*', # алгоритмы
    r'.*(interface|component|module|package|library).*',  # компоненты
    r'.*(plugin|extension|addon|widget|tool|utility).*',  # расширения
    r'.*(script|macro|automation|workflow|pipeline).*',   # автоматизация
    r'.*(config|setting|option|parameter|variable).*',    # настройки
    r'.*(state|status|condition|context|environment).*',  # состояния
    r'.*(event|trigger|handler|listener|observer).*',     # события
    r'.*(message|notification|alert|warning|error|info).*', # сообщения
    r'.*(request|response|callback|promise|async|await).*', # асинхронность
    r'.*(thread|process|fork|spawn|kill|signal).*',       # процессы
    r'.*(memory|heap|stack|pointer|reference|address).*', # память
    r'.*(cpu|gpu|ram|disk|ssd|hdd|nvme).*',               # железо
    r'.*(bandwidth|latency|throughput|performance|optimization).*', # производительность
    r'.*(security|privacy|anonymity|encryption|authentication).*', # безопасность
    r'.*(backup|restore|recovery|rollback|snapshot).*',   # резервное копирование
    r'.*(migration|deployment|release|version|update).*', # деплой
    r'.*(testing|qa|quality|assurance|validation).*',     # тестирование
    r'.*(documentation|manual|guide|tutorial|example).*', # документация
    r'.*(support|help|assistance|service|maintenance).*', # поддержка
    r'.*(consulting|advisory|coaching|mentoring|training).*', # консалтинг
    r'.*(strategy|planning|analysis|forecast|projection).*', # стратегия
    r'.*(marketing|advertising|promotion|campaign|seo).*', # маркетинг
    r'.*(sales|selling|closing|negotiation|contract).*',  # продажи
    r'.*(customer|user|client|consumer|audience).*',      # клиенты
    r'.*(product|solution|offer|proposal|pitch).*',       # продукты
    r'.*(innovation|creativity|invention|discovery|breakthrough).*', # инновации
    r'.*(leadership|management|administration|supervision).*', # лидерство
    r'.*(communication|collaboration|coordination|integration).*', # коммуникация
    r'.*(culture|values|mission|vision|purpose).*',       # культура
    r'.*(ethics|morality|responsibility|accountability).*', # этика
    r'.*(sustainability|ecology|environment|climate).*',  # устойчивость
    r'.*(diversity|inclusion|equality|fairness).*',       # разнообразие
    r'.*(wellbeing|happiness|satisfaction|engagement).*', # благополучие
    r'.*(growth|development|progress|advancement).*',     # рост
    r'.*(change|transformation|evolution|revolution).*',  # изменения
    r'.*(challenge|opportunity|risk|reward).*',           # вызовы
    r'.*(success|achievement|accomplishment|victory).*',  # успех
    r'.*(failure|mistake|lesson|experience).*',           # неудачи
    r'.*(learning|knowledge|wisdom|understanding).*',     # обучение
    r'.*(skill|talent|ability|capability|competence).*',  # навыки
    r'.*(motivation|inspiration|passion|drive).*',        # мотивация
    r'.*(discipline|focus|concentration|attention).*',    # дисциплина
    r'.*(patience|perseverance|resilience|strength).*',   # терпение
    r'.*(confidence|self-esteem|pride|honor).*',          # уверенность
    r'.*(humility|modesty|simplicity|elegance).*',        # скромность
    r'.*(generosity|kindness|compassion|empathy).*',      # щедрость
    r'.*(loyalty|trust|faithfulness|commitment).*',       # лояльность
    r'.*(respect|admiration|appreciation|gratitude).*',   # уважение
    r'.*(forgiveness|mercy|tolerance|acceptance).*',      # прощение
    r'.*(justice|fairness|equality|balance).*',           # справедливость
    r'.*(freedom|liberty|independence|autonomy).*',       # свобода
    r'.*(peace|calm|serenity|tranquility).*',             # мир
    r'.*(joy|happiness|pleasure|delight).*',              # радость
    r'.*(love|affection|attachment|bond).*',              # любовь
    r'.*(hope|faith|belief|trust).*',                     # надежда
    r'.*(courage|bravery|boldness|daring).*',             # храбрость
    r'.*(wisdom|intelligence|knowledge|understanding).*', # мудрость
    r'.*(beauty|aesthetics|artistry|craftsmanship).*',    # красота
    r'.*(truth|reality|authenticity|honesty).*',          # истина
    r'.*(meaning|purpose|significance|importance).*',     # смысл
    r'.*(connection|relationship|interaction|exchange).*', # связь
    r'.*(harmony|balance|symmetry|proportion).*',         # гармония
    r'.*(unity|wholeness|completeness|perfection).*',     # единство
    r'.*(infinity|eternity|immortality|boundlessness).*', # бесконечность
    r'.*(creation|origin|source|beginning).*',            # творение
    r'.*(destruction|end|termination|conclusion).*',      # разрушение
    r'.*(birth|death|life|existence).*',                  # жизнь
    r'.*(consciousness|awareness|mindfulness|presence).*', # сознание
    r'.*(subconscious|unconscious|instinct|intuition).*', # подсознание
    r'.*(dream|vision|imagination|fantasy).*',            # сны
    r'.*(reality|illusion|appearance|surface).*',         # реальность
    r'.*(material|physical|tangible|concrete).*',         # материал
    r'.*(spiritual|metaphysical|abstract|conceptual).*',  # духовное
    r'.*(natural|organic|wild|primitive).*',              # природное
    r'.*(artificial|synthetic|manufactured|constructed).*', # искусственное
    r'.*(simple|basic|elementary|fundamental).*',         # простое
    r'.*(complex|complicated|intricate|sophisticated).*', # сложное
    r'.*(clear|obvious|evident|manifest).*',              # ясное
    r'.*(hidden|secret|mysterious|enigmatic).*',          # скрытое
    r'.*(known|familiar|common|ordinary).*',              # известное
    r'.*(unknown|mysterious|strange|unusual).*',          # неизвестное
    r'.*(possible|probable|likely|feasible).*',           # возможное
    r'.*(impossible|unlikely|improbable|inconceivable).*', # невозможное
    r'.*(necessary|required|essential|vital).*',          # необходимое
    r'.*(optional|extra|additional|surplus).*',           # дополнительное
    r'.*(primary|secondary|tertiary|quaternary).*',       # первичное
    r'.*(major|minor|significant|trivial).*',             # важное
    r'.*(central|peripheral|marginal|boundary).*',        # центральное
    r'.*(internal|external|inside|outside).*',            # внутреннее
    r'.*(upper|lower|higher|lower).*',                    # верхнее
    r'.*(left|right|front|back).*',                       # левое
    r'.*(near|far|close|distant).*',                      # близкое
    r'.*(early|late|before|after).*',                     # раннее
    r'.*(young|old|new|ancient).*',                       # молодое
    r'.*(strong|weak|powerful|fragile).*',                # сильное
    r'.*(hard|soft|rigid|flexible).*',                    # твердое
    r'.*(heavy|light|dense|sparse).*',                    # тяжелое
    r'.*(fast|slow|quick|gradual).*',                     # быстрое
    r'.*(loud|quiet|silent|noise).*',                     # громкое
    r'.*(bright|dim|dark|shiny).*',                       # яркое
    r'.*(hot|cold|warm|cool).*',                          # горячее
    r'.*(wet|dry|moist|arid).*',                          # мокрое
    r'.*(smooth|rough|flat|bumpy).*',                     # гладкое
    r'.*(sharp|blunt|pointed|rounded).*',                 # острое
    r'.*(clean|dirty|pure|polluted).*',                   # чистое
    r'.*(fresh|stale|rotten|spoiled).*',                  # свежее
    r'.*(healthy|sick|ill|diseased).*',                   # здоровое
    r'.*(alive|dead|living|nonliving).*',                 # живое
    r'.*(real|fake|true|false).*',                        # настоящее
    r'.*(genuine|authentic|original|copy).*',             # подлинное
    r'.*(legitimate|illegal|valid|invalid).*',            # законное
    r'.*(proper|correct|accurate|precise).*',             # правильное
    r'.*(wrong|incorrect|erroneous|faulty).*',            # неправильное
    r'.*(good|bad|positive|negative).*',                  # хорошее
    r'.*(better|worse|improved|declined).*',              # лучшее
    r'.*(best|worst|optimal|suboptimal).*',               # лучшее
    r'.*(more|less|most|least).*',                        # больше
    r'.*(many|few|much|little).*',                        # много
    r'.*(all|none|some|any).*',                           # все
    r'.*(every|each|single|individual).*',                # каждый
    r'.*(whole|part|piece|fragment).*',                   # целое
    r'.*(complete|partial|full|empty).*',                 # полное
    r'.*(solid|liquid|gas|plasma).*',                     # твердое
    r'.*(matter|energy|force|field).*',                   # материя
    r'.*(particle|wave|quantum|relativistic).*',          # частица
    r'.*(atom|molecule|compound|element).*',              # атом
    r'.*(electron|proton|neutron|photon).*',              # электрон
    r'.*(gravity|electromagnetic|nuclear|weak).*',        # гравитация
    r'.*(motion|velocity|acceleration|momentum).*',       # движение
    r'.*(position|location|coordinate|vector).*',         # позиция
    r'.*(direction|orientation|angle|rotation).*',        # направление
    r'.*(distance|length|width|height).*',                # расстояние
    r'.*(area|volume|mass|weight).*',                     # площадь
    r'.*(density|pressure|temperature|entropy).*',        # плотность
    r'.*(time|duration|interval|frequency).*',            # время
    r'.*(period|cycle|oscillation|vibration).*',          # период
    r'.*(phase|stage|step|level).*',                      # фаза
    r'.*(order|sequence|series|progression).*',           # порядок
    r'.*(chaos|random|probability|statistics).*',         # хаос
    r'.*(information|data|knowledge|wisdom).*',           # информация
    r'.*(signal|noise|interference|distortion).*',        # сигнал
    r'.*(channel|medium|carrier|transport).*',            # канал
    r'.*(encoder|decoder|modulator|demodulator).*',       # энкодер
    r'.*(amplitude|frequency|wavelength|spectrum).*',     # амплитуда
    r'.*(resolution|precision|accuracy|fidelity).*',      # разрешение
    r'.*(compression|decompression|encoding|decoding).*', # сжатие
    r'.*(encryption|decryption|cipher|plaintext).*',      # шифрование
    r'.*(hash|digest|checksum|signature).*',              # хеш
    r'.*(key|password|credential|certificate).*',         # ключ
    r'.*(identity|authentication|authorization|access).*', # идентичность
    r'.*(permission|privilege|role|group).*',             # разрешение
    r'.*(session|cookie|token|ticket).*',                 # сессия
    r'.*(transaction|operation|procedure|function).*',    # транзакция
    r'.*(commit|rollback|savepoint|checkpoint).*',        # коммит
    r'.*(lock|mutex|semaphore|barrier).*',                # блокировка
    r'.*(race|condition|deadlock|livelock).*',            # гонка
    r'.*(priority|scheduler|dispatcher|allocator).*',     # приоритет
    r'.*(interrupt|exception|fault|trap).*',              # прерывание
    r'.*(syscall|ioctl|pipe|socket).*',                   # системный вызов
    r'.*(file|directory|inode|descriptor).*',             # файл
    r'.*(stream|buffer|cache|pool).*',                    # поток
    r'.*(iterator|generator|coroutine|fiber).*',          # итератор
    r'.*(closure|lambda|callback|hook).*',                # замыкание
    r'.*(object|class|instance|prototype).*',             # объект
    r'.*(method|property|attribute|field).*',             # метод
    r'.*(inheritance|polymorphism|encapsulation|abstraction).*', # наследование
    r'.*(composition|aggregation|association|dependency).*', # композиция
    r'.*(interface|implementation|instantiation|initialization).*', # интерфейс
    r'.*(constructor|destructor|finalizer|garbage).*',    # конструктор
    r'.*(allocation|deallocation|leak|fragmentation).*',  # распределение
    r'.*(pointer|reference|handle|identifier).*',         # указатель
    r'.*(array|list|stack|queue).*',                      # массив
    r'.*(tree|graph|map|set).*',                          # дерево
    r'.*(hash|trie|b-tree|skip-list).*',                  # хеш-таблица
    r'.*(sort|search|filter|reduce).*',                   # сортировка
    r'.*(merge|split|join|concatenate).*',                # слияние
    r'.*(parse|serialize|marshal|encode).*',              # парсинг
    r'.*(validate|sanitize|normalize|canonicalize).*',    # валидация
    r'.*(compile|interpret|execute|evaluate).*',          # компиляция
    r'.*(optimize|minify|bundle|pack).*',                 # оптимизация
    r'.*(debug|profile|benchmark|measure).*',             # отладка
    r'.*(test|assert|expect|mock).*',                     # тестирование
    r'.*(coverage|mutation|fuzz|stress).*',               # покрытие
    r'.*(continuous|integration|delivery|deployment).*',  # непрерывная интеграция
    r'.*(container|docker|kubernetes|orchestrator).*',    # контейнер
    r'.*(microservice|monolith|serverless|function).*',   # микросервис
    r'.*(api|rest|graphql|grpc).*',                       # API
    r'.*(endpoint|route|controller|handler).*',           # эндпоинт
    r'.*(middleware|proxy|gateway|bridge).*',             # middleware
    r'.*(database|sql|nosql|olap).*',                     # база данных
    r'.*(table|row|column|index).*',                      # таблица
    r'.*(query|statement|procedure|trigger).*',           # запрос
    r'.*(schema|model|entity|relation).*',                # схема
    r'.*(migration|seed|fixture|factory).*',              # миграция
    r'.*(orm|mapper|repository|unit-of-work).*',          # ORM
    r'.*(cache|memcached|redis|varnish).*',               # кэш
    r'.*(queue|rabbitmq|kafka|celery).*',                 # очередь
    r'.*(worker|job|task|cron).*',                        # воркер
    r'.*(scheduler|timer|delay|retry).*',                 # планировщик
    r'.*(monitor|logger|tracer|profiler).*',              # мониторинг
    r'.*(dashboard|metric|counter|histogram).*',          # дашборд
    r'.*(alert|alarm|threshold|baseline).*',              # алерт
    r'.*(incident|outage|downtime|sla).*',                # инцидент
    r'.*(postmortem|retrospective|review|audit).*',       # постмортем
    r'.*(architecture|design|pattern|practice).*',        # архитектура
    r'.*(scalability|availability|reliability|maintainability).*', # масштабируемость
    r'.*(performance|efficiency|resource|utilization).*', # производительность
    r'.*(security|privacy|compliance|governance).*',      # безопасность
    r'.*(usability|accessibility|internationalization|localization).*', # удобство использования
    r'.*(feature|requirement|specification|user-story).*', # функция
    r'.*(epic|story|task|bug).*',                         # эпик
    r'.*(sprint|iteration|release|milestone).*',          # спринт
    r'.*(backlog|roadmap|timeline|schedule).*',           # бэклог
    r'.*(kanban|scrum|xp|lean).*',                        # канбан
    r'.*(agile|iterative|incremental|adaptive).*',        # гибкий
    r'.*(waterfall|traditional|predictive|plan-driven).*', # водопад
    r'.*(hybrid|mixed|combined|integrated).*',            # гибридный
    r'.*(custom|bespoke|tailored|personalized).*',        # пользовательский
    r'.*(generic|universal|standard|default).*',          # общий
    r'.*(specific|particular|special|unique).*',          # конкретный
    r'.*(general|common|typical|normal).*',               # общий
    r'.*(special|exclusive|premium|luxury).*',            # специальный
    r'.*(basic|essential|minimum|entry-level).*',         # базовый
    r'.*(advanced|professional|expert|master).*',         # продвинутый
    r'.*(beginner|novice|amateur|learner).*',             # новичок
    r'.*(intermediate|average|middle|regular).*',         # средний
    r'.*(senior|junior|lead|principal).*',                # старший
    r'.*(manager|director|vp|ceo).*',                     # менеджер
    r'.*(founder|owner|creator|inventor).*',              # основатель
    r'.*(developer|programmer|coder|hacker).*',           # разработчик
    r'.*(designer|artist|illustrator|architect).*',       # дизайнер
    r'.*(analyst|researcher|scientist|scholar).*',        # аналитик
    r'.*(engineer|technician|mechanic|operator).*',       # инженер
    r'.*(administrator|sysadmin|devops|sre).*',           # администратор
    r'.*(tester|qa|validator|verifier).*',                # тестировщик
    r'.*(writer|editor|author|poet).*',                   # писатель
    r'.*(speaker|presenter|facilitator|moderator).*',     # оратор
    r'.*(teacher|mentor|coach|trainer).*',                # учитель
    r'.*(student|pupil|apprentice|intern).*',             # студент
    r'.*(patient|client|customer|consumer).*',            # пациент
    r'.*(doctor|physician|surgeon|therapist).*',          # врач
    r'.*(lawyer|attorney|judge|jury).*',                  # юрист
    r'.*(accountant|bookkeeper|auditor|taxpayer).*',      # бухгалтер
    r'.*(broker|agent|dealer|merchant).*',                # брокер
    r'.*(investor|shareholder|stakeholder|beneficiary).*', # инвестор
    r'.*(entrepreneur|businessman|tycoon|magnate).*',     # предприниматель
    r'.*(executive|officer|official|authority).*',        # руководитель
    r'.*(employee|staff|worker|laborer).*',               # сотрудник
    r'.*(employer|boss|supervisor|manager).*',            # работодатель
    r'.*(colleague|coworker|peer|associate).*',           # коллега
    r'.*(partner|spouse|family|relative).*',              # партнер
    r'.*(friend|acquaintance|neighbor|citizen).*',        # друг
    r'.*(enemy|opponent|rival|adversary).*',              # враг
    r'.*(ally|supporter|fan|follower).*',                 # союзник
    r'.*(leader|commander|captain|chief).*',              # лидер
    r'.*(member|participant|attendee|visitor).*',         # участник
    r'.*(guest|host|owner|tenant).*',                     # гость
    r'.*(player|gamer|athlete|competitor).*',             # игрок
    r'.*(winner|loser|champion|runner-up).*',             # победитель
    r'.*(hero|villain|protagonist|antagonist).*',         # герой
    r'.*(character|persona|avatar|profile).*',            # персонаж
    r'.*(identity|self|ego|soul).*',                      # личность
    r'.*(mind|brain|thought|idea).*',                     # разум
    r'.*(heart|emotion|feeling|passion).*',               # сердце
    r'.*(body|physical|material|corporal).*',             # тело
    r'.*(spirit|ghost|phantom|specter).*',                # дух
    r'.*(angel|demon|god|devil).*',                       # ангел
    r'.*(heaven|hell|paradise|abyss).*',                  # рай
    r'.*(light|darkness|day|night).*',                    # свет
    r'.*(good|evil|right|wrong).*',                       # добро
    r'.*(beautiful|ugly|pretty|plain).*',                 # красивый
    r'.*(perfect|flawless|ideal|excellent).*',            # идеальный
    r'.*(imperfect|defective|broken|damaged).*',          # несовершенный
    r'.*(complete|finished|done|ended).*',                # завершенный
    r'.*(incomplete|unfinished|ongoing|continuing).*',    # незавершенный
    r'.*(starting|beginning|opening|initiating).*',       # начинающий
    r'.*(ending|finishing|closing|terminating).*',        # заканчивающий
    r'.*(creating|making|building|constructing).*',       # создающий
    r'.*(destroying|breaking|removing|eliminating).*',    # разрушающий
    r'.*(saving|preserving|protecting|guarding).*',       # сохраняющий
    r'.*(losing|missing|forgetting|ignoring).*',          # теряющий
    r'.*(finding|discovering|revealing|uncovering).*',    # находящий
    r'.*(hiding|concealing|covering|masking).*',          # скрывающий
    r'.*(showing|displaying|presenting|demonstrating).*', # показывающий
    r'.*(telling|explaining|describing|narrating).*',     # рассказывающий
    r'.*(asking|inquiring|questioning|demanding).*',      # спрашивающий
    r'.*(answering|replying|responding|reacting).*',      # отвечающий
    r'.*(listening|hearing|paying attention|observing).*', # слушающий
    r'.*(speaking|talking|communicating|expressing).*',   # говорящий
    r'.*(reading|studying|examining|analyzing).*',        # читающий
    r'.*(writing|composing|drafting|editing).*',          # пишущий
    r'.*(thinking|pondering|reflecting|contemplating).*', # думающий
    r'.*(feeling|sensing|experiencing|perceiving).*',     # чувствующий
    r'.*(knowing|understanding|comprehending|grasping).*', # знающий
    r'.*(believing|trusting|having faith|accepting).*',   # верующий
    r'.*(hoping|wishing|desiring|wanting).*',             # надеющийся
    r'.*(loving|liking|enjoying|appreciating).*',         # любящий
    r'.*(hating|disliking|detesting|despising).*',        # ненавидящий
    r'.*(fearing|dreading|panicking|terrifying).*',       # боящийся
    r'.*(caring|concerning|worrying|bothering).*',        # заботящийся
    r'.*(sharing|giving|donating|contributing).*',        # делящийся
    r'.*(taking|stealing|grabbing|seizing).*',            # берущий
    r'.*(keeping|holding|retaining|maintaining).*',       # хранящий
    r'.*(throwing|casting|dropping|releasing).*',         # бросающий
    r'.*(catching|grabbing|seizing|capturing).*',         # ловящий
    r'.*(pushing|pulling|dragging|hauling).*',            # толкающий
    r'.*(lifting|raising|elevating|hoisting).*',          # поднимающий
    r'.*(lowering|dropping|descending|sinking).*',        # опускающий
    r'.*(moving|traveling|going|coming).*',               # двигающийся
    r'.*(staying|remaining|waiting|lingering).*',         # остающийся
    r'.*(leaving|departing|exiting|escaping).*',          # уходящий
    r'.*(arriving|reaching|landing|touching down).*',     # прибывающий
    r'.*(entering|joining|participating|engaging).*',     # входящий
    r'.*(avoiding|evading|dodging|ducking).*',            # избегающий
    r'.*(approaching|nearing|closing in|advancing).*',    # приближающийся
    r'.*(retreating|withdrawing|falling back|retiring).*', # отступающий
    r'.*(attacking|assaulting|charging|rushing).*',       # атакующий
    r'.*(defending|protecting|guarding|shielding).*',     # защищающий
    r'.*(fighting|battling|struggling|wrestling).*',      # сражающийся
    r'.*(agreeing|consenting|accepting|acknowledging).*', # соглашающийся
    r'.*(disagreeing|rejecting|denying|refusing).*',      # несоглашающийся
    r'.*(compromising|negotiating|settling|resolving).*', # идущий на компромисс
    r'.*(persuading|convincing|influencing|manipulating).*', # убеждающий
    r'.*(leading|guiding|directing|commanding).*',        # ведущий
    r'.*(following|obeying|complying|submitting).*',      # следующий
    r'.*(teaching|educating|instructing|training).*',     # обучающий
    r'.*(learning|studying|absorbing|acquiring).*',       # учащийся
    r'.*(remembering|recalling|recollecting|memorizing).*', # запоминающий
    r'.*(forgetting|overlooking|neglecting|ignoring).*',  # забывающий
    r'.*(imagining|visualizing|envisioning|fantasizing).*', # воображающий
    r'.*(creating|inventing|innovating|designing).*',     # создающий
    r'.*(imitating|copying|replicating|reproducing).*',   # имитирующий
    r'.*(transforming|changing|altering|modifying).*',    # преобразующий
    r'.*(preserving|conserving|saving|protecting).*',     # сохраняющий
    r'.*(destroying|ruining|wrecking|demolishing).*',     # разрушающий
    r'.*(repairing|fixing|mending|restoring).*',          # ремонтирующий
    r'.*(building|constructing|erecting|assembling).*',   # строящий
    r'.*(planting|sowing|cultivating|growing).*',         # сажающий
    r'.*(harvesting|reaping|gathering|collecting).*',     # собирающий урожай
    r'.*(eating|consuming|devouring|swallowing).*',       # едящий
    r'.*(drinking|sipping|gulping|chugging).*',           # пьющий
    r'.*(breathing|inhaling|exhaling|puffing).*',         # дышащий
    r'.*(sleeping|resting|dozing|napping).*',             # спящий
    r'.*(waking|rising|getting up|standing).*',           # просыпающийся
    r'.*(working|laboring|toiling|slaving).*',            # работающий
    r'.*(playing|having fun|enjoying oneself|recreating).*', # играющий
    r'.*(resting|relaxing|unwinding|chilling).*',         # отдыхающий
    r'.*(exercising|training|working out|stretching).*',  # тренирующийся
    r'.*(meditating|contemplating|reflecting|praying).*', # медитирующий
    r'.*(thinking|reasoning|analyzing|evaluating).*',     # думающий
    r'.*(feeling|sensing|experiencing|undergoing).*',     # чувствующий
    r'.*(knowing|understanding|comprehending|grasping).*', # знающий
    r'.*(believing|trusting|having faith|accepting).*',   # верующий
    r'.*(hoping|wishing|desiring|wanting).*',             # надеющийся
    r'.*(loving|liking|enjoying|appreciating).*',         # любящий
    r'.*(hating|disliking|detesting|despising).*',        # ненавидящий
    r'.*(fearing|dreading|panicking|terrifying).*',       # боящийся
    r'.*(caring|concerning|worrying|bothering).*',        # заботящийся
    r'.*(sharing|giving|donating|contributing).*',        # делящийся
    r'.*(taking|stealing|grabbing|seizing).*',            # берущий
    r'.*(keeping|holding|retaining|maintaining).*',       # хранящий
    r'.*(throwing|casting|dropping|releasing).*',         # бросающий
    r'.*(catching|grabbing|seizing|capturing).*',         # ловящий
    r'.*(pushing|pulling|dragging|hauling).*',            # толкающий
    r'.*(lifting|raising|elevating|hoisting).*',          # поднимающий
    r'.*(lowering|dropping|descending|sinking).*',        # опускающий
    r'.*(moving|traveling|going|coming).*',               # двигающийся
    r'.*(staying|remaining|waiting|lingering).*',         # остающийся
    r'.*(leaving|departing|exiting|escaping).*',          # уходящий
    r'.*(arriving|reaching|landing|touching down).*',     # прибывающий
    r'.*(entering|joining|participating|engaging).*',     # входящий
    r'.*(avoiding|evading|dodging|ducking).*',            # избегающий
    r'.*(approaching|nearing|closing in|advancing).*',    # приближающийся
    r'.*(retreating|withdrawing|falling back|retiring).*', # отступающий
    r'.*(attacking|assaulting|charging|rushing).*',       # атакующий
    r'.*(defending|protecting|guarding|shielding).*',     # защищающий
    r'.*(fighting|battling|struggling|wrestling).*',      # сражающийся
    r'.*(agreeing|consenting|accepting|acknowledging).*', # соглашающийся
    r'.*(disagreeing|rejecting|denying|refusing).*',      # несоглашающийся
    r'.*(compromising|negotiating|settling|resolving).*', # идущий на компромисс
    r'.*(persuading|convincing|influencing|manipulating).*', # убеждающий
    r'.*(leading|guiding|directing|commanding).*',        # ведущий
    r'.*(following|obeying|complying|submitting).*',      # следующий
    r'.*(teaching|educating|instructing|training).*',     # обучающий
    r'.*(learning|studying|absorbing|acquiring).*',       # учащийся
    r'.*(remembering|recalling|recollecting|memorizing).*', # запоминающий
    r'.*(forgetting|overlooking|neglecting|ignoring).*',  # забывающий
    r'.*(imagining|visualizing|envisioning|fantasizing).*', # воображающий
    r'.*(creating|inventing|innovating|designing).*',     # создающий
    r'.*(imitating|copying|replicating|reproducing).*',   # имитирующий
    r'.*(transforming|changing|altering|modifying).*',    # преобразующий
    r'.*(preserving|conserving|saving|protecting).*',     # сохраняющий
    r'.*(destroying|ruining|wrecking|demolishing).*',     # разрушающий
    r'.*(repairing|fixing|mending|restoring).*',          # ремонтирующий
    r'.*(building|constructing|erecting|assembling).*',   # строящий
    r'.*(planting|sowing|cultivating|growing).*',         # сажающий
    r'.*(harvesting|reaping|gathering|collecting).*',     # собирающий урожай
    r'.*(eating|consuming|devouring|swallowing).*',       # едящий
    r'.*(drinking|sipping|gulping|chugging).*',           # пьющий
    r'.*(breathing|inhaling|exhaling|puffing).*',         # дышащий
    r'.*(sleeping|resting|dozing|napping).*',             # спящий
    r'.*(waking|rising|getting up|standing).*',           # просыпающийся
    r'.*(working|laboring|toiling|slaving).*',            # работающий
    r'.*(playing|having fun|enjoying oneself|recreating).*', # играющий
    r'.*(resting|relaxing|unwinding|chilling).*',         # отдыхающий
    r'.*(exercising|training|working out|stretching).*',  # тренирующийся
    r'.*(meditating|contemplating|reflecting|praying).*', # медитирующий
    r'.*(thinking|reasoning|analyzing|evaluating).*',     # думающий
    r'.*(feeling|sensing|experiencing|undergoing).*',     # чувствующий
    r'.*(knowing|understanding|comprehending|grasping).*', # знающий
    r'.*(believing|trusting|having faith|accepting).*',   # верующий
    r'.*(hoping|wishing|desiring|wanting).*',             # надеющийся
    r'.*(loving|liking|enjoying|appreciating).*',         # любящий
    r'.*(hating|disliking|detesting|despising).*',        # ненавидящий
    r'.*(fearing|dreading|panicking|terrifying).*',       # боящийся
    r'.*(caring|concerning|worrying|bothering).*',        # заботящийся
    r'.*(sharing|giving|donating|contributing).*',        # делящийся
    r'.*(taking|stealing|grabbing|seizing).*',            # берущий
    r'.*(keeping|holding|retaining|maintaining).*',       # хранящий
    r'.*(throwing|casting|dropping|releasing).*',         # бросающий
    r'.*(catching|grabbing|seizing|capturing).*',         # ловящий
    r'.*(pushing|pulling|dragging|hauling).*',            # толкающий
    r'.*(lifting|raising|elevating|hoisting).*',          # поднимающий
    r'.*(lowering|dropping|descending|sinking).*',        # опускающий
    r'.*(moving|traveling|going|coming).*',               # двигающийся
    r'.*(staying|remaining|waiting|lingering).*',         # остающийся
    r'.*(leaving|departing|exiting|escaping).*',          # уходящий
    r'.*(arriving|reaching|landing|touching down).*',     # прибывающий
    r'.*(entering|joining|participating|engaging).*',     # входящий
    r'.*(avoiding|evading|dodging|ducking).*',            # избегающий
    r'.*(approaching|nearing|closing in|advancing).*',    # приближающийся
    r'.*(retreating|withdrawing|falling back|retiring).*', # отступающий
    r'.*(attacking|assaulting|charging|rushing).*',       # атакующий
    r'.*(defending|protecting|guarding|shielding).*',     # защищающий
    r'.*(fighting|battling|struggling|wrestling).*',      # сражающийся
    r'.*(agreeing|consenting|accepting|acknowledging).*', # соглашающийся
    r'.*(disagreeing|rejecting|denying|refusing).*',      # несоглашающийся
    r'.*(compromising|negotiating|settling|resolving).*', # идущий на компромисс
    r'.*(persuading|convincing|influencing|manipulating).*', # убеждающий
    r'.*(leading|guiding|directing|commanding).*',        # ведущий
    r'.*(following|obeying|complying|submitting).*',      # следующий
    r'.*(teaching|educating|instructing|training).*',     # обучающий
    r'.*(learning|studying|absorbing|acquiring).*',       # учащийся
    r'.*(remembering|recalling|recollecting|memorizing).*', # запоминающий
    r'.*(forgetting|overlooking|neglecting|ignoring).*',  # забывающий
    r'.*(imagining|visualizing|envisioning|fantasizing).*', # воображающий
    r'.*(creating|inventing|innovating|designing).*',     # создающий
    r'.*(imitating|copying|replicating|reproducing).*',   # имитирующий
    r'.*(transforming|changing|altering|modifying).*',    # преобразующий
    r'.*(preserving|conserving|saving|protecting).*',     # сохраняющий
    r'.*(destroying|ruining|wrecking|demolishing).*',     # разрушающий
    r'.*(repairing|fixing|mending|restoring).*',          # ремонтирующий
    r'.*(building|constructing|erecting|assembling).*',   # строящий
    r'.*(planting|sowing|cultivating|growing).*',         # сажающий
    r'.*(harvesting|reaping|gathering|collecting).*',     # собирающий урожай
    r'.*(eating|consuming|devouring|swallowing).*',       # едящий
    r'.*(drinking|sipping|gulping|chugging).*',           # пьющий
    r'.*(breathing|inhaling|exhaling|puffing).*',         # дышащий
    r'.*(sleeping|resting|dozing|napping).*',             # спящий
    r'.*(waking|rising|getting up|standing).*',           # просыпающийся
    r'.*(working|laboring|toiling|slaving).*',            # работающий
    r'.*(playing|having fun|enjoying oneself|recreating).*', # играющий
    r'.*(resting|relaxing|unwinding|chilling).*',         # отдыхающий
    r'.*(exercising|training|working out|stretching).*',  # тренирующийся
    r'.*(meditating|contemplating|reflecting|praying).*', # медитирующий
]

tg_client = None
http_session = None
auto_on = False
check_counter = 0
found_set = set()
watch_set = set()
subs_dict = {}
refs_dict = {}
result_cache = {}

PLANS = {
    "1h": {"name": "1 Hour", "rub": 10, "stars": 5, "delta": timedelta(hours=1)},
    "1d": {"name": "1 Day", "rub": 50, "stars": 25, "delta": timedelta(days=1)},
    "7d": {"name": "7 Days", "rub": 100, "stars": 50, "delta": timedelta(days=7)},
    "life": {"name": "Lifetime", "rub": 500, "stars": 250, "delta": None},
}

def load_data():
    global found_set, watch_set, subs_dict, refs_dict
    if os.path.exists(FOUND_FILE):
        with open(FOUND_FILE) as f: found_set = set(json.load(f))
    if os.path.exists(WATCH_FILE):
        with open(WATCH_FILE) as f: watch_set = set(json.load(f))
    else:
        watch_set = {"admin", "crypto", "ton", "btc"}
        save_watch()
    if os.path.exists(SUBS_FILE):
        with open(SUBS_FILE) as f: subs_dict = json.load(f)
    if os.path.exists(REF_FILE):
        with open(REF_FILE) as f: refs_dict = json.load(f)

def save_found():
    with open(FOUND_FILE, "w") as f: json.dump(list(found_set), f)
def save_watch():
    with open(WATCH_FILE, "w") as f: json.dump(list(watch_set), f)
def save_subs():
    with open(SUBS_FILE, "w") as f: json.dump(subs_dict, f)
def save_refs():
    with open(REF_FILE, "w") as f: json.dump(refs_dict, f)

def is_subscribed(uid):
    if str(uid) == str(OWNER_ID): return True
    val = subs_dict.get(str(uid))
    if not val: return False
    if val == "lifetime": return True
    try:
        return datetime.fromisoformat(val) > datetime.now()
    except: return False

def grant_sub(uid, plan_key):
    p = PLANS[plan_key]
    if p["delta"] is None:
        subs_dict[str(uid)] = "lifetime"
    else:
        base = datetime.now()
        cur = subs_dict.get(str(uid))
        if cur and cur != "lifetime":
            try:
                d = datetime.fromisoformat(cur)
                if d > base: base = d
            except: pass
        subs_dict[str(uid)] = (base + p["delta"]).isoformat()
    save_subs()

def get_ref_code(uid):
    for code, data in refs_dict.items():
        if data.get("owner") == uid: return code
    code = hashlib.md5(str(uid).encode()).hexdigest()[:8]
    refs_dict[code] = {"owner": uid, "invited": [], "pending": {}}
    save_refs()
    return code

def gen_name():
    """Генерирует имя из 7 букв (без цифр!)"""
    letters = list("abcdefghijklmnopqrstuvwxyz")
    return "".join(random.choice(letters) for _ in range(NAME_LENGTH)).lower()

def is_beautiful(username):
    """Проверяет, является ли имя красивым по паттернам"""
    if len(username) != NAME_LENGTH:
        return False
    
    # Проверяем против всех паттернов
    for pattern in BEAUTIFUL_PATTERNS:
        if re.match(pattern, username):
            return True
    
    # Дополнительные проверки красоты
    vowels = set('aeiou')
    consonants = set('bcdfghjklmnpqrstvwxyz')
    
    # Чередование гласных и согласных
    vowel_count = sum(1 for c in username if c in vowels)
    consonant_count = sum(1 for c in username if c in consonants)
    
    # Хорошее соотношение гласных/согласных
    if 2 <= vowel_count <= 4 and 3 <= consonant_count <= 5:
        return True
    
    # Нет трех одинаковых подряд
    for i in range(len(username)-2):
        if username[i] == username[i+1] == username[i+2]:
            return False
    
    # Нет запрещенных комбинаций
    bad_combos = ['fuck', 'shit', 'damn', 'ass', 'bitch', 'cunt']
    for combo in bad_combos:
        if combo in username:
            return False
    
    return False

def estimate_price(username):
    """Оценивает стоимость юзернейма как на Fragment"""
    length = len(username)
    
    # Базовая цена по длине
    base_prices = {
        4: 1000,
        5: 500,
        6: 200,
        7: 100,
        8: 50,
        9: 25,
        10: 10
    }
    
    price = base_prices.get(length, 5)
    
    # Множитель за красоту
    if is_beautiful(username):
        price *= 3  # Красивые имена дороже в 3 раза
    
    # Множитель за редкость букв
    rare_letters = set('qzxjk')
    rare_count = sum(1 for c in username if c in rare_letters)
    if rare_count > 0:
        price *= (1 + rare_count * 0.2)
    
    # Множитель за наличие популярных слов
    popular_words = ['the', 'and', 'for', 'you', 'can', 'her', 'his', 'was', 'one', 'our', 'out', 'all', 'may', 'how', 'its', 'now', 'day', 'get', 'has', 'him', 'his', 'man', 'see', 'two', 'way', 'who', 'boy', 'did', 'yes', 'let', 'go', 'be', 'to', 'of', 'in', 'that', 'have', 'this', 'will', 'your', 'from', 'they', 'know', 'want', 'been', 'good', 'much', 'some', 'into', 'just', 'time', 'very', 'when', 'come', 'here', 'what', 'take', 'than', 'them', 'look', 'many', 'then', 'turn', 'over', 'only', 'year', 'made', 'these', 'even', 'where', 'because', 'thing', 'really', 'about', 'should', 'never', 'under', 'while', 'might', 'those', 'could', 'other', 'until', 'since', 'without', 'again', 'against', 'between', 'through', 'during', 'before', 'after', 'above', 'below', 'up', 'down', 'out', 'off', 'on', 'by', 'with', 'as', 'is', 'are', 'am', 'was', 'were', 'has', 'had', 'have', 'does', 'did', 'do', 'will', 'would', 'shall', 'should', 'may', 'might', 'must', 'can', 'could', 'need', 'dare', 'ought', 'used']
    
    word_bonus = 0
    for word in popular_words:
        if word in username:
            word_bonus += 1
    
    if word_bonus > 0:
        price *= (1 + word_bonus * 0.1)
    
    # Округляем до ближайших $10
    return round(price / 10) * 10

async def init_http():
    global http_session
    if not http_session:
        connector = TCPConnector(limit=100, ttl_dns_cache=300)
        headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/90 Mobile Safari/537.36"}
        http_session = ClientSession(connector=connector, headers=headers, timeout=__import__('aiohttp').ClientTimeout(total=HTTP_TIMEOUT))

def check_cache(username):
    if username in result_cache:
        is_free, timestamp = result_cache[username]
        if time.time() - timestamp < CACHE_TTL: return is_free
    return None

async def check_free_fast(username):
    cached = check_cache(username)
    if cached is not None: return cached
    global http_session
    if not http_session: await init_http()
    try:
        async with http_session.head(f"https://t.me/{username}", allow_redirects=False) as r:
            if r.status == 404:
                result_cache[username] = (True, time.time())
                return True
    except: pass
    global tg_client
    if tg_client and tg_client.is_connected():
        try:
            await tg_client.get_entity(username)
            result_cache[username] = (False, time.time())
            return False
        except ValueError:
            result_cache[username] = (True, time.time())
            return True
        except: pass
    result_cache[username] = (False, time.time())
    return False

async def hunter_loop(app_bot):
    global auto_on, check_counter, found_set
    while True:
        if not auto_on:
            await asyncio.sleep(2)
            continue
        
        batch = []
        attempts = 0
        max_attempts = BATCH_SIZE * 3  # Максимум попыток найти красивые имена
        
        while len(batch) < BATCH_SIZE and attempts < max_attempts:
            u = gen_name()
            if u not in found_set and u not in result_cache:
                # Фильтруем только красивые имена!
                if is_beautiful(u):
                    batch.append(u)
            attempts += 1
        
        if not batch:
            await asyncio.sleep(0.5)
            continue
        
        tasks = [check_free_fast(u) for u in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for username, is_free in zip(batch, results):
            if isinstance(is_free, Exception): continue
            check_counter += 1
            if is_free:
                found_set.add(username)
                save_found()
                print(f"FOUND @{username} (Beautiful!)")
                try:
                    await app_bot.bot.send_message(OWNER_ID, f"NEW FIND:\n@{username}\nTotal: {len(found_set)}\nEst. Value: ${estimate_price(username)}")
                except: pass
        
        await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

# ═══════════ WEB SERVER (MIUI STYLE) ═══════════

async def serve_static(request):
    path = request.match_info.get('path', '')
    if not path or path == '/':
        path = 'index.html'
    file_path = os.path.join('web', path)
    if not os.path.exists(file_path) or os.path.isdir(file_path):
        return web.Response(status=404, text='Not found')
    mime = {'html':'text/html', 'css':'text/css', 'js':'application/javascript'}
    with open(file_path, 'rb') as f: content = f.read()
    return web.Response(body=content, content_type=mime.get(path.split('.')[-1], 'text/plain'))

async def api_stats(request):
    recent_finds = list(found_set)[-10:]  # Последние 10 находок
    return web.json_response({
        "checked_count": check_counter,
        "found_count": len(found_set),
        "auto_on": auto_on,
        "watch_list": list(watch_set)[:20],
        "recent_finds": recent_finds,
        "prices": {name: estimate_price(name) for name in recent_finds}
    })

async def api_command(request):
    global auto_on
    data = await request.json()
    cmd = data.get('command', '')
    if '/on' in cmd: auto_on = True
    elif '/off' in cmd: auto_on = False
    elif '/add' in cmd:
        parts = cmd.split()
        if len(parts) > 1:
            watch_set.add(parts[1].lstrip('@').lower())
            save_watch()
    elif '/remove' in cmd:
        parts = cmd.split()
        if len(parts) > 1:
            name = parts[1].lstrip('@').lower()
            if name in watch_set:
                watch_set.remove(name)
                save_watch()
    return web.json_response({"success": True})

# ═══════════ BOT HANDLERS ═══════════

def main_menu_kb(uid, is_hunting=False):
    btn_hunt = InlineKeyboardButton("STOP HUNT", callback_data="hunt_off") if is_hunting else InlineKeyboardButton("START HUNT", callback_data="hunt_on")
    keyboard = [
        [InlineKeyboardButton("OPEN DASHBOARD", web_app={"url": MINI_APP_URL})],
        [btn_hunt],
        [InlineKeyboardButton("GENERATOR", callback_data="gen"), InlineKeyboardButton("CHECK", callback_data="check_ask")],
        [InlineKeyboardButton("SUBSCRIPTION", callback_data="sub"), InlineKeyboardButton("REFERRALS", callback_data="ref")],
        [InlineKeyboardButton("PROFILE", callback_data="profile"), InlineKeyboardButton("VIP", callback_data="vip")],
        [InlineKeyboardButton("CONTACT", url=OWNER_LINK)]
    ]
    return InlineKeyboardMarkup(keyboard)

def sub_menu_kb():
    btns = []
    for key, p in PLANS.items():
        btns.append([InlineKeyboardButton(f"{p['name']} - {p['rub']}RUB / {p['stars']}Stars", callback_data=f"pay_{key}")])
    btns.append([InlineKeyboardButton("BACK", callback_data="back_main")])
    return InlineKeyboardMarkup(btns)

def pay_method_kb(plan):
    p = PLANS[plan]
    btns = [
        [InlineKeyboardButton(f"CryptoBot ({p['rub']}RUB)", callback_data=f"m_crypto_{plan}")],
        [InlineKeyboardButton(f"Stars ({p['stars']})", callback_data=f"m_stars_{plan}")],
        [InlineKeyboardButton("BACK", callback_data="sub")]
    ]
    return InlineKeyboardMarkup(btns)

async def cmd_start(update, context):
    uid = update.effective_user.id
    msg = "USERNAME HUNTER PRO\n\nSmart search for beautiful nicknames\nFast - Safe - Reliable\nOnly 7-letter names without numbers!\n\nChoose action:"
    await update.message.reply_text(msg, reply_markup=main_menu_kb(uid, auto_on))

async def callback_handler(update, context):
    global auto_on
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id
    if data == "back_main":
        await query.edit_message_reply_markup(reply_markup=main_menu_kb(uid, auto_on))
    elif data == "hunt_on":
        if not is_subscribed(uid) and uid != OWNER_ID:
            await query.answer("Need subscription!", show_alert=True)
            return
        auto_on = True
        await query.edit_message_text("HUNT STARTED!\n\nSearching only beautiful 7-letter names...\nNo numbers, no ugly patterns.\nLogs in Termux\nFinds will come here\n\nMenu:", reply_markup=main_menu_kb(uid, True))
    elif data == "hunt_off":
        auto_on = False
        await query.edit_message_text(f"HUNT STOPPED\n\nChecked: {check_counter}\nFound: {len(found_set)}\nAll finds are beautiful 7-letter names!\n\nMenu:", reply_markup=main_menu_kb(uid, False))
    elif data == "gen":
        if not is_subscribed(uid) and uid != OWNER_ID:
            await query.answer("Need subscription!", show_alert=True)
            return
        names = []
        attempts = 0
        while len(names) < FREE_BATCH and attempts < 50:
            u = gen_name()
            if is_beautiful(u):
                names.append(u)
            attempts += 1
        if not names:
            # Fallback to regular generation if no beautiful ones found quickly
            names = [gen_name() for _ in range(FREE_BATCH)]
        text = "BEAUTIFUL GENERATOR\n\nOnly 7-letter names without numbers:\n\n" + "\n".join([f"- @{n} (${estimate_price(n)})" for n in names]) + "\n\nMenu:"
        await query.edit_message_text(text, reply_markup=main_menu_kb(uid, auto_on))
    elif data == "check_ask":
        await query.edit_message_text("CHECK USERNAME\n\nSend me username to check:\nExample: admin\n\nWe'll tell you if it's available and its estimated value!")
        context.user_data["waiting_check"] = True
    elif data == "sub":
        await query.edit_message_text("SUBSCRIPTION PLANS\n\nUnlimited beautiful search\nPriority speed\nVIP monitoring\nUnlimited generator\n\nChoose plan:", reply_markup=sub_menu_kb())
    elif data.startswith("pay_"):
        plan = data.split("_")[1]
        p = PLANS[plan]
        await query.edit_message_text(f"PAYMENT\n\n{p['name']}\nPrice: {p['rub']}RUB or {p['stars']}Stars\n\nChoose method:", reply_markup=pay_method_kb(plan))
    elif data.startswith("m_crypto_"):
        plan = data.split("_")[2]
        p = PLANS[plan]
        if not CRYPTO_BOT_TOKEN:
            await query.answer("CryptoBot not configured", show_alert=True)
            return
        payload = f"sub_{uid}_{plan}"
        async with ClientSession(headers={"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}) as sess:
            resp = await sess.post("https://pay.crypt.bot/api/createInvoice", json={"currency_type": "fiat", "fiat": "RUB", "amount": str(p["rub"]), "payload": payload, "allow_comments": False})
            inv = await resp.json()
            if inv.get("ok"):
                url = inv["result"]["pay_url"]
                await query.edit_message_text(f"INVOICE CREATED\n\nSum: {p['rub']}RUB\nLink: {url}\n\nAfter payment subscription activates automatically")
            else:
                await query.answer("Invoice creation error", show_alert=True)
    elif data.startswith("m_stars_"):
        plan = data.split("_")[2]
        p = PLANS[plan]
        await context.bot.send_invoice(chat_id=uid, title=p["name"], description=f"Subscription {p['name']}", payload=f"sub_{uid}_{plan}", provider_token="", currency="XTR", prices=[LabeledPrice(label="Access", amount=p["stars"])])
    elif data == "ref":
        code = get_ref_code(uid)
        link = f"https://t.me/{context.bot.username}?start={code}"
        ref_data = refs_dict.get(code, {})
        invited = len(ref_data.get("invited", []))
        text = f"REFERRAL PROGRAM\n\n+1 HOUR for each friend!\n\nInvited: {invited}\nEarned: {invited}h\n\nYour link:\n{link}\n\nMenu:"
        await query.edit_message_text(text, reply_markup=main_menu_kb(uid, auto_on))
    elif data == "profile":
        sub_status = "Lifetime" if subs_dict.get(str(uid)) == "lifetime" else ("No access" if not is_subscribed(uid) else "Active")
        text = f"PROFILE\n\nID: {uid}\nStatus: {sub_status}\nChecked: {check_counter}\nFound: {len(found_set)}\nAll finds are beautiful 7-letter names!\n\nMenu:"
        await query.edit_message_text(text, reply_markup=main_menu_kb(uid, auto_on))
    elif data == "vip":
        if not is_subscribed(uid) and uid != OWNER_ID:
            await query.answer("Need subscription!", show_alert=True)
            return
        vip_list = "\n".join([f"- @{n}" for n in list(watch_set)[:10]])
        text = f"VIP MONITOR\n\nTracked names:\n\n{vip_list}\n\nMenu:"
        await query.edit_message_text(text, reply_markup=main_menu_kb(uid, auto_on))

async def handle_message(update, context):
    if context.user_data.get("waiting_check"):
        context.user_data["waiting_check"] = False
        text = update.message.text.strip().lstrip("@").lower()
        await update.message.reply_text(f"Checking @{text}...")
        is_free = await check_free_fast(text)
        price = estimate_price(text)
        beauty = "Beautiful!" if is_beautiful(text) else "Regular"
        if is_free:
            await update.message.reply_text(f"FREE - @{text}\nEstimated Value: ${price}\nType: {beauty}")
        else:
            await update.message.reply_text(f"TAKEN - @{text}\nEstimated Market Value: ${price}\nType: {beauty}")

async def precheckout(update, context):
    await update.pre_checkout_query.answer(ok=True)

async def successful_payment(update, context):
    msg = update.effective_message
    payload = msg.successful_payment.invoice_payload
    if payload.startswith("sub_"):
        _, uid, plan = payload.split("_", 2)
        grant_sub(int(uid), plan)
        p = PLANS[plan]
        await msg.reply_text(f"PAYMENT RECEIVED!\n\nSubscription {p['name']} activated!\nNow you can search unlimited beautiful 7-letter names!")

async def crypto_poller(app_bot):
    if not CRYPTO_BOT_TOKEN: return
    seen = set()
    while True:
        try:
            async with ClientSession(headers={"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}) as sess:
                async with sess.get("https://pay.crypt.bot/api/getInvoices", params={"state": "paid"}) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for inv in (data.get("result", {}).get("items", []) if data.get("ok") else []):
                            iid = inv["invoice_id"]
                            if iid in seen or inv.get("status") != "paid": continue
                            seen.add(iid)
                            payload = inv.get("payload", "")
                            if payload.startswith("sub_"):
                                _, uid, plan = payload.split("_", 2)
                                grant_sub(int(uid), plan)
                                p = PLANS[plan]
                                try:
                                    await app_bot.bot.send_message(int(uid), f"PAYMENT RECEIVED!\n\nSubscription {p['name']} activated!\nNow you can search unlimited beautiful 7-letter names!")
                                except: pass
        except: pass
        await asyncio.sleep(10)

async def main():
    global tg_client
    tg_client = TelegramClient('session_hunter', API_ID, API_HASH)
    await tg_client.start(bot_token=BOT_TOKEN)
    load_data()
    await init_http()
    
    app_web = web.Application()
    app_web.router.add_get('/{path:.*}', serve_static)
    app_web.router.add_post('/api/command', api_command)
    app_web.router.add_get('/api/stats', api_stats)
    runner = web.AppRunner(app_web)
    await runner.setup()
    await web.TCPSite(runner, host='0.0.0.0', port=8080).start()
    print("WEB SERVER READY on port 8080")
    
    app_bot = Application.builder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", cmd_start))
    app_bot.add_handler(CallbackQueryHandler(callback_handler))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app_bot.add_handler(PreCheckoutQueryHandler(precheckout))
    app_bot.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    await app_bot.initialize()
    await app_bot.start()
    await app_bot.updater.start_polling()
    print("BOT READY")
    
    await asyncio.gather(hunter_loop(app_bot), crypto_poller(app_bot))

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutting down...")
