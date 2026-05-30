"""
KeyWise AI — Smart Word Validator
Local English dictionary, edit-distance spell checker, and correction
validation engine.

Three layers of intelligence:
  1. DICTIONARY CHECK — Skip API entirely for known valid English words
  2. LOCAL CORRECTION — Fix obvious typos instantly (<1ms) using
     Peter Norvig-style edit-distance candidates
  3. POST-API GUARD  — Validate Groq's corrections using Levenshtein
     distance, first-letter anchoring, and length-ratio checks to
     reject rewrites disguised as corrections

Zero external dependencies.  Pure Python.
"""
import threading


# ── Levenshtein distance ────────────────────────────────────────────────────────
def levenshtein(s1: str, s2: str) -> int:
    """Compute the Levenshtein (edit) distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost is 0 if characters match, 1 otherwise
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(
                curr_row[j] + 1,         # Insert
                prev_row[j + 1] + 1,     # Delete
                prev_row[j] + cost,      # Replace
            ))
        prev_row = curr_row

    return prev_row[-1]


# ── Common English words dictionary (~3000 words) ──────────────────────────────
# This set covers the vast majority of everyday English vocabulary.
# Any word found here is considered correctly spelled and will NEVER
# be sent to the Groq API for correction.
_COMMON_ENGLISH: frozenset = frozenset({
    # ── A ──
    'a', 'abandon', 'ability', 'able', 'about', 'above', 'abroad',
    'absence', 'absent', 'absolute', 'absolutely', 'absorb', 'abstract',
    'abuse', 'academic', 'accept', 'acceptable', 'access', 'accident',
    'accompany', 'accomplish', 'according', 'account', 'accurate',
    'accuse', 'achieve', 'achievement', 'acid', 'acknowledge', 'acquire',
    'across', 'act', 'action', 'active', 'activist', 'activity', 'actor',
    'actual', 'actually', 'ad', 'adapt', 'add', 'addition', 'additional',
    'address', 'adequate', 'adjust', 'adjustment', 'administration',
    'administrator', 'admire', 'admit', 'adopt', 'adult', 'advance',
    'advanced', 'advantage', 'adventure', 'advice', 'advise', 'adviser',
    'advocate', 'affair', 'affect', 'afford', 'afraid', 'after',
    'afternoon', 'again', 'against', 'age', 'agency', 'agenda', 'agent',
    'aggressive', 'ago', 'agree', 'agreement', 'ahead', 'aid', 'aim',
    'air', 'aircraft', 'airline', 'airport', 'alarm', 'album', 'alcohol',
    'alien', 'align', 'alive', 'all', 'alliance', 'allow', 'ally',
    'almost', 'alone', 'along', 'already', 'also', 'alter', 'alternative',
    'although', 'always', 'amazing', 'ambition', 'ambitious', 'among',
    'amount', 'amuse', 'analysis', 'analyst', 'analyze', 'ancient',
    'and', 'anger', 'angle', 'angry', 'animal', 'ankle', 'anniversary',
    'announce', 'annual', 'another', 'answer', 'anticipate', 'anxiety',
    'anxious', 'any', 'anybody', 'anymore', 'anyone', 'anything',
    'anyway', 'anywhere', 'apart', 'apartment', 'apparent', 'apparently',
    'appeal', 'appear', 'appearance', 'apple', 'application', 'apply',
    'appoint', 'appointment', 'appreciate', 'approach', 'appropriate',
    'approval', 'approve', 'approximately', 'april', 'area', 'argue',
    'argument', 'arise', 'arm', 'army', 'around', 'arrange', 'arrangement',
    'arrest', 'arrival', 'arrive', 'arrow', 'art', 'article', 'artist',
    'as', 'aside', 'ask', 'asleep', 'aspect', 'assault', 'assert',
    'assess', 'assessment', 'asset', 'assign', 'assignment', 'assist',
    'assistance', 'assistant', 'associate', 'association', 'assume',
    'assumption', 'assure', 'at', 'atmosphere', 'attach', 'attack',
    'attain', 'attempt', 'attend', 'attention', 'attitude', 'attorney',
    'attract', 'attractive', 'attribute', 'audience', 'august', 'aunt',
    'author', 'authority', 'auto', 'available', 'average', 'avoid',
    'award', 'aware', 'awareness', 'away', 'awful',
    'analogy', 'analog', 'analogous', 'anatomy', 'anchor', 'angel',
    'anonymous', 'antenna', 'antique', 'anxiety', 'ape', 'apex',
    'apology', 'apparatus', 'apparel', 'appetite', 'appliance',
    'arithmetic', 'armor', 'aroma', 'artificial', 'aspect', 'aspire',
    'assembly', 'assertion', 'asset', 'asteroid', 'astronomy',
    'atmosphere', 'atom', 'attic', 'auction', 'audit', 'authentic',
    'avenue', 'aviation', 'avocado', 'awesome', 'availability',

    # ── B ──
    'baby', 'back', 'background', 'backward', 'bacon', 'bad', 'badly',
    'bag', 'bake', 'balance', 'ball', 'ban', 'band', 'bank', 'bar',
    'bare', 'barely', 'barn', 'barrel', 'barrier', 'base', 'baseball',
    'basic', 'basically', 'basis', 'basket', 'basketball', 'bathroom',
    'battery', 'battle', 'be', 'beach', 'bean', 'bear', 'beard', 'beat',
    'beautiful', 'beauty', 'because', 'become', 'bed', 'bedroom', 'beef',
    'been', 'beer', 'before', 'begin', 'beginning', 'behavior', 'behind',
    'being', 'belief', 'believe', 'bell', 'belong', 'below', 'bench',
    'bend', 'beneath', 'benefit', 'beside', 'besides', 'best', 'bet',
    'better', 'between', 'beyond', 'bible', 'bicycle', 'big', 'bike',
    'bill', 'billion', 'bind', 'bird', 'birth', 'birthday', 'bit',
    'bite', 'bitter', 'black', 'blade', 'blame', 'blank', 'blanket',
    'blast', 'bleed', 'blend', 'bless', 'blind', 'block', 'blood',
    'blow', 'blue', 'board', 'boat', 'body', 'bomb', 'bond', 'bone',
    'book', 'boom', 'boot', 'border', 'born', 'borrow', 'boss', 'both',
    'bother', 'bottle', 'bottom', 'bounce', 'bound', 'boundary', 'bowl',
    'box', 'boy', 'boyfriend', 'brain', 'branch', 'brand', 'brave',
    'bread', 'break', 'breakfast', 'breast', 'breath', 'breathe', 'breed',
    'brick', 'bridge', 'brief', 'briefly', 'bright', 'brilliant', 'bring',
    'broad', 'broadcast', 'broken', 'brother', 'brown', 'brush', 'buck',
    'budget', 'bug', 'build', 'builder', 'building', 'bullet', 'bunch',
    'burden', 'burn', 'burst', 'bury', 'bus', 'business', 'busy', 'but',
    'butter', 'button', 'buy', 'buyer', 'by',
    'badge', 'bamboo', 'banana', 'bandwidth', 'banner', 'bargain',
    'basket', 'batch', 'beacon', 'beam', 'beast', 'behalf', 'beloved',
    'berry', 'beverage', 'biography', 'bizarre', 'blade', 'bless',
    'bliss', 'blossom', 'blueprint', 'bluff', 'bonus', 'booking',
    'booth', 'botanical', 'boulder', 'bouquet', 'boutique', 'bracket',
    'breeze', 'brochure', 'bronze', 'bruise', 'bubble', 'buckle',
    'buffet', 'bulletin', 'bumper', 'bundle', 'bureau', 'burger',
    'butterfly', 'bypass', 'better', 'best', 'before', 'behind',
    'below', 'beside', 'between',

    # ── C ──
    'cabin', 'cabinet', 'cable', 'cake', 'calculate', 'call', 'calm',
    'camera', 'camp', 'campaign', 'campus', 'can', 'cancel', 'cancer',
    'candidate', 'cap', 'capable', 'capacity', 'capital', 'captain',
    'capture', 'car', 'carbon', 'card', 'care', 'career', 'careful',
    'carefully', 'carpet', 'carry', 'case', 'cash', 'cast', 'cat',
    'catalog', 'catch', 'category', 'cause', 'celebrate', 'celebration',
    'cell', 'center', 'central', 'century', 'ceremony', 'certain',
    'certainly', 'chain', 'chair', 'chairman', 'challenge', 'chamber',
    'champion', 'championship', 'chance', 'chancellor', 'change',
    'channel', 'chapter', 'character', 'characteristic', 'charge',
    'charity', 'chart', 'chase', 'cheap', 'check', 'cheek', 'cheese',
    'chef', 'chemical', 'chest', 'chicken', 'chief', 'child', 'children',
    'chin', 'chip', 'chocolate', 'choice', 'choose', 'church', 'circle',
    'circumstance', 'cite', 'citizen', 'city', 'civil', 'civilian',
    'claim', 'class', 'classic', 'classroom', 'clean', 'clear', 'clearly',
    'client', 'climate', 'climb', 'clinic', 'clinical', 'clock', 'close',
    'closely', 'closer', 'clothes', 'cloud', 'club', 'clue', 'cluster',
    'coach', 'coalition', 'coast', 'coat', 'code', 'coffee', 'cognitive',
    'cold', 'collapse', 'colleague', 'collect', 'collection', 'college',
    'colonial', 'colony', 'color', 'column', 'combination', 'combine',
    'come', 'comfort', 'comfortable', 'command', 'commander', 'comment',
    'commercial', 'commission', 'commit', 'commitment', 'committee',
    'common', 'communicate', 'communication', 'community', 'companion',
    'company', 'compare', 'comparison', 'compete', 'competition',
    'competitive', 'competitor', 'complain', 'complaint', 'complete',
    'completely', 'complex', 'complexity', 'complicate', 'component',
    'compose', 'composition', 'comprehensive', 'computer', 'concentrate',
    'concentration', 'concept', 'concern', 'concerned', 'concert',
    'conclude', 'conclusion', 'concrete', 'condition', 'conduct',
    'conference', 'confidence', 'confident', 'confirm', 'conflict',
    'confront', 'confusion', 'congress', 'connect', 'connection',
    'conscious', 'consciousness', 'consensus', 'consequence',
    'conservative', 'consider', 'considerable', 'consideration',
    'consist', 'consistent', 'constant', 'constantly', 'constitute',
    'constitutional', 'construct', 'construction', 'consultant',
    'consume', 'consumer', 'consumption', 'contact', 'contain',
    'container', 'contemporary', 'content', 'contest', 'context',
    'continue', 'contract', 'contrast', 'contribute', 'contribution',
    'control', 'controversial', 'controversy', 'convention',
    'conventional', 'conversation', 'conversion', 'convert', 'conviction',
    'convince', 'cook', 'cookie', 'cooking', 'cool', 'cooperation',
    'cop', 'cope', 'copy', 'core', 'corn', 'corner', 'corporate',
    'corporation', 'correct', 'correction', 'correspond', 'correspondent',
    'corresponding', 'cost', 'cotton', 'couch', 'could', 'council',
    'count', 'counter', 'country', 'county', 'couple', 'courage',
    'course', 'court', 'cousin', 'cover', 'coverage', 'crack', 'craft',
    'crash', 'crazy', 'cream', 'create', 'creation', 'creative',
    'creature', 'credit', 'crew', 'crime', 'criminal', 'crisis',
    'criteria', 'critic', 'critical', 'criticism', 'crop', 'cross',
    'crowd', 'crucial', 'cry', 'cultural', 'culture', 'cup', 'curious',
    'current', 'currently', 'curriculum', 'curve', 'custom', 'customer',
    'cut', 'cycle',
    'cage', 'calcium', 'calendar', 'camouflage', 'candle', 'canvas',
    'canyon', 'capsule', 'caravan', 'cardboard', 'cargo', 'carnival',
    'carpet', 'carriage', 'cascade', 'cassette', 'castle', 'casual',
    'catalogue', 'catastrophe', 'caution', 'cavalry', 'ceiling',
    'celestial', 'census', 'ceramic', 'cereal', 'chaos', 'chapel',
    'charm', 'chassis', 'cherish', 'chess', 'chimney', 'chorus',
    'chronicle', 'chunk', 'cinnamon', 'circuit', 'circular', 'circus',
    'civic', 'civilization', 'clarity', 'clash', 'clause', 'clergy',
    'clever', 'cliff', 'climax', 'clinic', 'closure', 'cloth',
    'coalition', 'cocktail', 'coconut', 'coil', 'coincidence', 'collar',
    'colony', 'colossal', 'combat', 'comedy', 'comet', 'commodity',
    'commonwealth', 'compact', 'compass', 'compel', 'compile',
    'complement', 'compliance', 'compliment', 'compound', 'compromise',
    'compulsory', 'conceal', 'conceive', 'condense', 'confess',
    'confine', 'congratulate', 'conscience', 'consecutive', 'consent',
    'conserve', 'console', 'conspiracy', 'constrain', 'consul',
    'contemplate', 'contempt', 'contend', 'continent', 'contradict',
    'convenience', 'converse', 'convey', 'cooperative', 'coordinate',
    'copper', 'coral', 'cord', 'cork', 'corpse', 'corridor', 'corrupt',
    'cosmic', 'costume', 'cottage', 'counsel', 'courtesy', 'cousin',
    'covenant', 'coward', 'cradle', 'crane', 'crater', 'crawl',
    'creature', 'credential', 'creed', 'cricket', 'crisp', 'criterion',
    'critique', 'crocodile', 'cruise', 'crumble', 'crush', 'crystal',
    'cuisine', 'cultivate', 'cunning', 'cupboard', 'curb', 'curiosity',
    'curtain', 'custody', 'cylinder', 'cooking', 'cookie',

    # ── D ──
    'dad', 'daily', 'damage', 'dance', 'danger', 'dangerous', 'dare',
    'dark', 'darkness', 'data', 'database', 'date', 'daughter', 'day',
    'dead', 'deal', 'dealer', 'dear', 'death', 'debate', 'debt',
    'decade', 'december', 'decent', 'decide', 'decision', 'deck',
    'declare', 'decline', 'decrease', 'deep', 'deeply', 'deer',
    'defeat', 'defend', 'defendant', 'defense', 'defensive', 'deficit',
    'define', 'definitely', 'definition', 'degree', 'delay', 'delegate',
    'deliberate', 'delicate', 'deliver', 'delivery', 'demand',
    'democracy', 'democrat', 'democratic', 'demonstrate', 'demonstration',
    'deny', 'department', 'depend', 'dependent', 'depending', 'depict',
    'deploy', 'depression', 'deputy', 'derive', 'describe', 'description',
    'desert', 'deserve', 'design', 'designer', 'desire', 'desk',
    'desperate', 'despite', 'destroy', 'destruction', 'detail',
    'detailed', 'detect', 'determine', 'develop', 'developer',
    'development', 'device', 'devote', 'dialogue', 'diamond', 'diary',
    'die', 'diet', 'differ', 'difference', 'different', 'differently',
    'difficult', 'difficulty', 'dig', 'digital', 'dimension', 'dinner',
    'direct', 'direction', 'directly', 'director', 'dirt', 'dirty',
    'disability', 'disagree', 'disappear', 'disappoint', 'disaster',
    'discipline', 'discourse', 'discover', 'discovery', 'discrimination',
    'discuss', 'discussion', 'disease', 'dish', 'dismiss', 'disorder',
    'display', 'dispute', 'distance', 'distant', 'distinct', 'distinction',
    'distinguish', 'distribute', 'distribution', 'district', 'disturb',
    'diverse', 'diversity', 'divide', 'division', 'divorce', 'do',
    'doctor', 'document', 'dog', 'dollar', 'domain', 'domestic',
    'dominant', 'dominate', 'door', 'double', 'doubt', 'down', 'downtown',
    'dozen', 'draft', 'drag', 'drain', 'drama', 'dramatic',
    'dramatically', 'draw', 'drawing', 'dream', 'dress', 'drink',
    'drive', 'driver', 'drop', 'drug', 'dry', 'dual', 'due', 'dumb',
    'dump', 'during', 'dust', 'duty',
    'dagger', 'dawn', 'debris', 'debut', 'decimal', 'decisive',
    'dedication', 'deduction', 'defect', 'definite', 'delight',
    'delusion', 'demon', 'denial', 'dense', 'dental', 'depot',
    'depression', 'descendant', 'destiny', 'detach', 'detention',
    'deteriorate', 'determination', 'devastate', 'deviate', 'diagnose',
    'diagram', 'dialect', 'diameter', 'dictate', 'diesel', 'dignity',
    'dilemma', 'diligent', 'diminish', 'dinosaur', 'diploma', 'diplomat',
    'directory', 'discourse', 'discreet', 'discrete', 'disdain',
    'disguise', 'dislike', 'dismay', 'dispatch', 'disperse', 'displace',
    'disposal', 'dispose', 'dissolve', 'distort', 'distract', 'distress',
    'dividend', 'divine', 'doctrine', 'dolphin', 'dome', 'donate',
    'donor', 'doom', 'dormitory', 'dose', 'dough', 'dove', 'downfall',
    'download', 'drastic', 'drawback', 'dread', 'drought', 'drum',
    'duchess', 'duel', 'duke', 'dull', 'duplicate', 'durable', 'dusk',
    'dwarf', 'dwell', 'dynamic', 'dynasty',

    # ── E ──
    'each', 'eager', 'ear', 'early', 'earn', 'earning', 'earth', 'ease',
    'easily', 'east', 'eastern', 'easy', 'eat', 'echo', 'economic',
    'economy', 'edge', 'edition', 'editor', 'educate', 'education',
    'educator', 'effect', 'effective', 'effectively', 'efficiency',
    'efficient', 'effort', 'egg', 'eight', 'either', 'elaborate',
    'elderly', 'elect', 'election', 'electric', 'electricity', 'electron',
    'electronic', 'element', 'eliminate', 'elite', 'else', 'elsewhere',
    'email', 'embrace', 'emerge', 'emergency', 'emission', 'emotion',
    'emotional', 'emphasis', 'emphasize', 'empire', 'employ', 'employee',
    'employer', 'employment', 'empty', 'enable', 'encounter', 'encourage',
    'end', 'enemy', 'energy', 'enforce', 'engage', 'engine', 'engineer',
    'engineering', 'enhance', 'enjoy', 'enormous', 'enough', 'enroll',
    'ensure', 'enter', 'enterprise', 'entertainment', 'enthusiasm',
    'entire', 'entirely', 'entity', 'entrance', 'entrepreneur', 'entry',
    'environment', 'environmental', 'episode', 'equal', 'equally',
    'equipment', 'era', 'error', 'escape', 'especially', 'essay',
    'essential', 'essentially', 'establish', 'establishment', 'estate',
    'estimate', 'etc', 'ethics', 'ethnic', 'evaluate', 'evaluation',
    'even', 'evening', 'event', 'eventually', 'ever', 'every',
    'everybody', 'everyday', 'everyone', 'everything', 'everywhere',
    'evidence', 'evil', 'evolution', 'evolve', 'exact', 'exactly',
    'exam', 'examination', 'examine', 'example', 'exceed', 'excellent',
    'except', 'exception', 'exchange', 'excite', 'excitement', 'exciting',
    'exclude', 'exclusive', 'excuse', 'execute', 'executive', 'exercise',
    'exhibit', 'exhibition', 'exist', 'existence', 'existing', 'expand',
    'expansion', 'expect', 'expectation', 'expense', 'expensive',
    'experience', 'experiment', 'expert', 'explain', 'explanation',
    'explicit', 'explode', 'exploit', 'exploration', 'explore',
    'explosion', 'export', 'expose', 'exposure', 'express', 'expression',
    'extend', 'extension', 'extensive', 'extent', 'external', 'extra',
    'extraordinary', 'extreme', 'extremely', 'eye',
    'eagle', 'eclipse', 'ecology', 'ecosystem', 'edifice', 'editorial',
    'elaborate', 'elastic', 'elbow', 'elegant', 'elevate', 'eligible',
    'eloquent', 'embed', 'emblem', 'embryo', 'emerald', 'emigrate',
    'eminent', 'emit', 'empathy', 'emperor', 'empirical', 'empower',
    'empress', 'enchant', 'endorse', 'endurance', 'endure', 'enigma',
    'enlighten', 'enrich', 'ensemble', 'envision', 'enzyme', 'epidemic',
    'epilogue', 'equator', 'equity', 'equivalent', 'erode', 'erosion',
    'errand', 'erupt', 'escalate', 'espionage', 'essence', 'eternal',
    'ethical', 'etiquette', 'evacuate', 'evade', 'eventual', 'evergreen',
    'evict', 'evident', 'evoke', 'exaggerate', 'exalt', 'excavate',
    'excerpt', 'excessive', 'exclaim', 'exempt', 'exhaust', 'exile',
    'exotic', 'expedition', 'expenditure', 'expertise', 'expiration',
    'expire', 'exploit', 'exponent', 'extravagant', 'eyebrow',

    # ── F ──
    'fabric', 'face', 'facility', 'fact', 'factor', 'factory', 'faculty',
    'fail', 'failure', 'fair', 'fairly', 'faith', 'fall', 'false',
    'familiar', 'family', 'famous', 'fan', 'fancy', 'fantasy', 'far',
    'farm', 'farmer', 'fascinating', 'fashion', 'fast', 'fat', 'fate',
    'father', 'fault', 'favor', 'favorite', 'fear', 'feature', 'february',
    'federal', 'fee', 'feed', 'feel', 'feeling', 'fellow', 'female',
    'fence', 'festival', 'fever', 'few', 'fiber', 'fiction', 'field',
    'fifteen', 'fifth', 'fifty', 'fight', 'fighter', 'figure', 'file',
    'fill', 'film', 'filter', 'final', 'finally', 'finance', 'financial',
    'find', 'finding', 'fine', 'finger', 'finish', 'fire', 'firm',
    'first', 'fish', 'fit', 'five', 'fix', 'flag', 'flame', 'flash',
    'flat', 'flavor', 'flee', 'flesh', 'flexibility', 'flight', 'flip',
    'float', 'flood', 'floor', 'flow', 'flower', 'fly', 'focus', 'fold',
    'folk', 'follow', 'following', 'food', 'fool', 'foot', 'football',
    'for', 'force', 'foreign', 'forest', 'forever', 'forget', 'forgive',
    'form', 'formal', 'formation', 'former', 'formula', 'forth', 'fortune',
    'forward', 'found', 'foundation', 'founder', 'four', 'fourth',
    'fox', 'fraction', 'frame', 'framework', 'franchise', 'frank', 'free',
    'freedom', 'freeze', 'frequency', 'frequent', 'frequently', 'fresh',
    'friend', 'friendly', 'friendship', 'front', 'frozen', 'fruit',
    'frustrate', 'frustration', 'fuel', 'fulfill', 'full', 'fully',
    'fun', 'function', 'fund', 'fundamental', 'funding', 'funeral',
    'funny', 'furniture', 'furthermore', 'future',
    'fable', 'facade', 'facet', 'facilitate', 'faction', 'falcon',
    'famine', 'fanatic', 'farewell', 'fascinate', 'fatigue', 'fauna',
    'feasible', 'feast', 'feat', 'feather', 'feeble', 'feedback',
    'fertile', 'festive', 'feudal', 'fiasco', 'fidelity', 'fierce',
    'figurative', 'filament', 'finale', 'fireplace', 'fiscal',
    'fixture', 'flair', 'flank', 'flask', 'flaw', 'fledgling', 'fleet',
    'flexible', 'flicker', 'flora', 'flourish', 'fluctuate', 'fluent',
    'fluid', 'folklore', 'foolish', 'footprint', 'forecast', 'foresight',
    'forge', 'formidable', 'formulate', 'forsake', 'fortress', 'fossil',
    'foster', 'fragile', 'fragment', 'fragrance', 'frantic', 'fraud',
    'freight', 'frenzy', 'friction', 'fringe', 'frivolous', 'frontier',
    'frost', 'frugal', 'fugitive', 'furnace', 'fury', 'fusion', 'futile',

    # ── G ──
    'gain', 'galaxy', 'gallery', 'game', 'gang', 'gap', 'garage',
    'garden', 'garlic', 'gas', 'gate', 'gather', 'gay', 'gaze', 'gear',
    'gender', 'gene', 'general', 'generally', 'generate', 'generation',
    'genetic', 'genius', 'genre', 'gentle', 'gentleman', 'gently',
    'genuine', 'geography', 'gesture', 'get', 'ghost', 'giant', 'gift',
    'gifted', 'girl', 'girlfriend', 'give', 'given', 'glad', 'glance',
    'glass', 'global', 'globe', 'gloom', 'glory', 'glove', 'go', 'goal',
    'god', 'gold', 'golden', 'golf', 'gone', 'good', 'govern',
    'government', 'governor', 'grab', 'grace', 'grade', 'gradually',
    'graduate', 'grain', 'grand', 'grandfather', 'grandmother', 'grant',
    'grass', 'grateful', 'grave', 'gray', 'great', 'greatest', 'green',
    'greet', 'grey', 'grocery', 'ground', 'group', 'grow', 'growing',
    'growth', 'guarantee', 'guard', 'guess', 'guest', 'guide',
    'guideline', 'guilty', 'guitar', 'gun', 'gut', 'guy',
    'gadget', 'gallop', 'gamble', 'garment', 'garrison', 'gasp',
    'gateway', 'gauge', 'gazette', 'gem', 'genealogy', 'generalize',
    'generous', 'genetics', 'genocide', 'gentle', 'geology', 'geometry',
    'germ', 'gigantic', 'ginger', 'glacier', 'glamour', 'gleam', 'glide',
    'glimpse', 'glitter', 'gorgeous', 'gospel', 'gossip', 'gown',
    'grace', 'gradient', 'graft', 'grammar', 'granite', 'graphic',
    'grasp', 'gratitude', 'gravel', 'gravity', 'greed', 'greenhouse',
    'grief', 'grill', 'grim', 'grin', 'grip', 'groan', 'groove', 'gross',
    'grove', 'growl', 'grudge', 'grumble', 'grunt', 'guild', 'gust',
    'gymnasium', 'gypsy',

    # ── H ──
    'habit', 'habitat', 'hair', 'half', 'hall', 'halt', 'hand', 'handle',
    'handsome', 'hang', 'happen', 'happy', 'harbor', 'hard', 'hardly',
    'harm', 'harvest', 'hat', 'hate', 'hatred', 'have', 'he', 'head',
    'headline', 'headquarters', 'health', 'healthy', 'hear', 'hearing',
    'heart', 'heat', 'heaven', 'heavily', 'heavy', 'heel', 'height',
    'helicopter', 'hell', 'hello', 'help', 'helpful', 'her', 'here',
    'heritage', 'hero', 'herself', 'hesitate', 'hide', 'hierarchy',
    'high', 'highlight', 'highly', 'highway', 'hill', 'him', 'himself',
    'hip', 'hire', 'his', 'historian', 'historic', 'historical', 'history',
    'hit', 'hold', 'hole', 'holiday', 'holy', 'home', 'homeless',
    'homework', 'honest', 'honestly', 'honey', 'honor', 'hook', 'hope',
    'hopefully', 'horizon', 'horror', 'horse', 'hospital', 'host',
    'hostage', 'hostile', 'hot', 'hotel', 'hour', 'house', 'household',
    'housing', 'how', 'however', 'hub', 'huge', 'human', 'humor',
    'hundred', 'hungry', 'hunt', 'hunter', 'hurt', 'husband',
    'hallway', 'hamlet', 'hammer', 'handbook', 'handicap', 'handy',
    'harden', 'hardship', 'hardware', 'harmony', 'harness', 'harp',
    'harsh', 'haunt', 'haven', 'hazard', 'headache', 'heal', 'heap',
    'heartbeat', 'hedge', 'heir', 'hemisphere', 'hemp', 'herald',
    'herb', 'herd', 'heroic', 'heroine', 'hesitation', 'hibernate',
    'hidden', 'hike', 'hilarious', 'hinder', 'hinge', 'hint',
    'hippopotamus', 'hitch', 'hive', 'hoax', 'hobbit', 'hobby',
    'hollow', 'homestead', 'homicide', 'hone', 'hood', 'horoscope',
    'horrible', 'horrify', 'hospitable', 'hospitality', 'hostility',
    'hound', 'housewife', 'hover', 'howl', 'huddle', 'hull', 'humble',
    'humid', 'humiliate', 'humility', 'hurdle', 'hurricane', 'hustle',
    'hybrid', 'hydrogen', 'hygiene', 'hymn', 'hypothesis',

    # ── I ──
    'i', 'ice', 'idea', 'ideal', 'identify', 'identity', 'ideology',
    'if', 'ignore', 'ill', 'illegal', 'illness', 'illustrate',
    'illustration', 'image', 'imagination', 'imagine', 'immediate',
    'immediately', 'immigrant', 'immigration', 'impact', 'implement',
    'implementation', 'implication', 'imply', 'import', 'importance',
    'important', 'impose', 'impossible', 'impress', 'impression',
    'impressive', 'improve', 'improvement', 'in', 'incident', 'include',
    'including', 'income', 'incorporate', 'increase', 'increasingly',
    'incredible', 'incredibly', 'indeed', 'independence', 'independent',
    'index', 'indicate', 'indication', 'indicator', 'individual',
    'industrial', 'industry', 'infant', 'infection', 'inflation',
    'influence', 'inform', 'information', 'infrastructure', 'initial',
    'initially', 'initiative', 'injury', 'inner', 'innocent',
    'innovation', 'innovative', 'input', 'inquiry', 'insect', 'insert',
    'inside', 'insight', 'insist', 'inspire', 'install', 'instance',
    'instead', 'institution', 'institutional', 'instruction',
    'instructor', 'instrument', 'insurance', 'intellectual',
    'intelligence', 'intelligent', 'intend', 'intense', 'intensity',
    'intention', 'interact', 'interaction', 'interest', 'interested',
    'interesting', 'internal', 'international', 'internet', 'interpret',
    'interpretation', 'intervention', 'interview', 'into', 'introduce',
    'introduction', 'invade', 'invasion', 'invest', 'investigate',
    'investigation', 'investigator', 'investment', 'investor',
    'invisible', 'invitation', 'invite', 'involve', 'involved',
    'involvement', 'iron', 'irony', 'island', 'isolate', 'isolation',
    'issue', 'it', 'item', 'its', 'itself', 'ivory',
    'iceberg', 'icon', 'identical', 'idle', 'idol', 'ignite',
    'illuminate', 'illusion', 'immense', 'immerse', 'imminent',
    'immune', 'impair', 'imperial', 'implicit', 'impulse', 'inaugural',
    'incentive', 'incidence', 'incline', 'inclusive', 'incredible',
    'incur', 'indefinite', 'indigenous', 'indigo', 'induce', 'indulge',
    'inequality', 'inevitable', 'infamous', 'inferior', 'infinite',
    'inflict', 'influential', 'inherit', 'inhibit', 'injustice',
    'inmate', 'innate', 'inquire', 'insane', 'inscription', 'inspect',
    'inspiration', 'installment', 'instant', 'instinct', 'institute',
    'integrate', 'integrity', 'intercept', 'interfere', 'interim',
    'interior', 'intermediate', 'interval', 'intimate', 'intricate',
    'intrigue', 'intrinsic', 'intuition', 'invalid', 'invaluable',
    'inventory', 'inverse', 'invoice', 'invoke', 'irrigate', 'irritate',
    'isolate', 'ivory',

    # ── J ──
    'jacket', 'jail', 'jam', 'january', 'jar', 'jaw', 'jazz', 'jealous',
    'jeans', 'jet', 'jew', 'jewel', 'jewelry', 'job', 'join', 'joint',
    'joke', 'journal', 'journalist', 'journey', 'joy', 'judge',
    'judgment', 'juice', 'july', 'jump', 'june', 'junior', 'jury',
    'just', 'justice', 'justify',
    'javelin', 'jealousy', 'jeopardize', 'jersey', 'jest', 'jeweler',
    'jigsaw', 'jingle', 'jockey', 'jolly', 'jostle', 'jubilee',
    'judicial', 'juggle', 'jumble', 'junction', 'jungle', 'jurisdiction',
    'juvenile',

    # ── K ──
    'keen', 'keep', 'key', 'keyboard', 'kick', 'kid', 'kidnap', 'kidney',
    'kill', 'killer', 'killing', 'kind', 'king', 'kingdom', 'kiss',
    'kit', 'kitchen', 'knee', 'knife', 'knock', 'know', 'knowledge',
    'known',
    'kangaroo', 'keepsake', 'kernel', 'kerosene', 'kettle', 'kindle',
    'kinetic', 'knack', 'kneel', 'knit', 'knob', 'knot',

    # ── L ──
    'lab', 'label', 'labor', 'laboratory', 'lack', 'lady', 'lake',
    'land', 'landscape', 'lane', 'language', 'lap', 'large', 'largely',
    'laser', 'last', 'late', 'lately', 'later', 'latest', 'latin',
    'latter', 'laugh', 'laughter', 'launch', 'law', 'lawn', 'lawsuit',
    'lawyer', 'lay', 'layer', 'lead', 'leader', 'leadership', 'leading',
    'leaf', 'league', 'lean', 'learn', 'learning', 'least', 'leather',
    'leave', 'lecture', 'left', 'leg', 'legacy', 'legal', 'legend',
    'legislation', 'legitimate', 'leisure', 'lemon', 'length', 'lens',
    'less', 'lesson', 'let', 'letter', 'level', 'liberal', 'liberty',
    'library', 'license', 'lie', 'life', 'lifestyle', 'lifetime', 'lift',
    'light', 'like', 'likelihood', 'likely', 'likewise', 'limit',
    'limitation', 'limited', 'line', 'link', 'lion', 'lip', 'list',
    'listen', 'literally', 'literary', 'literature', 'little', 'live',
    'living', 'load', 'loan', 'lobby', 'local', 'locate', 'location',
    'lock', 'lodge', 'log', 'logic', 'logical', 'lonely', 'long', 'look',
    'loop', 'loose', 'lord', 'lose', 'loss', 'lost', 'lot', 'lots',
    'loud', 'love', 'lovely', 'lover', 'low', 'lower', 'luck', 'lucky',
    'lunch', 'lung',
    'labyrinth', 'lace', 'ladder', 'lag', 'lagoon', 'lamb', 'lament',
    'lamp', 'lance', 'landmark', 'landslide', 'lantern', 'lapse',
    'lark', 'larva', 'latch', 'lateral', 'latitude', 'lattice',
    'lavender', 'lavish', 'layout', 'ledge', 'legend', 'legion',
    'legislature', 'lend', 'leopard', 'lethal', 'lever', 'leverage',
    'levy', 'lexicon', 'liable', 'liaison', 'liar', 'liberate',
    'lieutenant', 'ligament', 'lighthouse', 'likewise', 'limb',
    'limestone', 'linen', 'linger', 'liquor', 'literacy', 'literal',
    'liturgy', 'livelihood', 'livestock', 'loathe', 'lobe', 'locomotive',
    'loft', 'longevity', 'longitude', 'loom', 'loophole', 'lottery',
    'lousy', 'loyalty', 'lubricant', 'lucid', 'luggage', 'lumber',
    'luminous', 'lunar', 'lure', 'lurk', 'lush', 'lust', 'luxury',
    'lyric',

    # ── M ──
    'machine', 'mad', 'magazine', 'magic', 'magical', 'magnificent',
    'mail', 'main', 'mainly', 'mainstream', 'maintain', 'maintenance',
    'major', 'majority', 'make', 'maker', 'male', 'mall', 'man',
    'manage', 'management', 'manager', 'manner', 'mansion', 'manual',
    'manufacturer', 'manufacturing', 'many', 'map', 'margin', 'mark',
    'market', 'marketing', 'marriage', 'married', 'marry', 'mask',
    'mass', 'massive', 'master', 'match', 'mate', 'material', 'math',
    'mathematics', 'matter', 'mature', 'maximum', 'may', 'maybe',
    'mayor', 'me', 'meal', 'mean', 'meaning', 'meaningful', 'means',
    'meanwhile', 'measure', 'measurement', 'meat', 'mechanism', 'media',
    'medical', 'medication', 'medicine', 'medium', 'meet', 'meeting',
    'member', 'membership', 'memo', 'memoir', 'memorial', 'memory',
    'mental', 'mention', 'mentor', 'menu', 'merchant', 'mere', 'merely',
    'merge', 'merit', 'mess', 'message', 'metal', 'metaphor', 'method',
    'methodology', 'middle', 'might', 'migration', 'mild', 'military',
    'milk', 'mill', 'million', 'mind', 'mine', 'mineral', 'minister',
    'ministry', 'minor', 'minority', 'minute', 'miracle', 'mirror',
    'miss', 'missile', 'mission', 'mistake', 'mix', 'mixture', 'mm',
    'mode', 'model', 'moderate', 'modern', 'modest', 'modify',
    'molecule', 'mom', 'moment', 'momentum', 'money', 'monitor', 'monk',
    'monkey', 'month', 'mood', 'moon', 'moral', 'more', 'moreover',
    'morning', 'mortgage', 'most', 'mostly', 'mother', 'motion',
    'motivation', 'motor', 'mount', 'mountain', 'mouse', 'mouth', 'move',
    'movement', 'movie', 'much', 'multiple', 'municipal', 'murder',
    'muscle', 'museum', 'music', 'musical', 'musician', 'muslim', 'must',
    'mutual', 'my', 'myself', 'mystery', 'myth',
    'madness', 'magnet', 'magnify', 'maiden', 'majesty', 'malice',
    'mammal', 'mandate', 'manifest', 'manipulate', 'mankind', 'mantle',
    'manuscript', 'maple', 'marathon', 'marble', 'march', 'marginal',
    'marine', 'marital', 'marker', 'martial', 'marvel', 'masculine',
    'massacre', 'massage', 'mast', 'mastery', 'matrix', 'meadow',
    'medieval', 'meditate', 'melody', 'membrane', 'memorable', 'menace',
    'mercury', 'mercy', 'mesh', 'metabolism', 'metric', 'metropolitan',
    'microphone', 'microscope', 'midfield', 'migrate', 'milestone',
    'militia', 'millennium', 'mimic', 'miniature', 'minimal', 'minimize',
    'mint', 'mischief', 'miserable', 'mislead', 'missionary', 'mist',
    'mobile', 'mobility', 'mockery', 'module', 'moist', 'moisture',
    'mold', 'monarchy', 'monastery', 'monopoly', 'monotone', 'monster',
    'monument', 'morale', 'morality', 'mortal', 'mosaic', 'mosque',
    'mosquito', 'moth', 'motive', 'motto', 'mound', 'mourn', 'mud',
    'muffin', 'mug', 'multimedia', 'multiply', 'mumble', 'mural',
    'murmur', 'mushroom', 'mustard', 'mute', 'mutter', 'mythology',

    # ── N ──
    'nail', 'naked', 'name', 'narrative', 'narrow', 'nation', 'national',
    'natural', 'naturally', 'nature', 'naval', 'navy', 'near', 'nearby',
    'nearly', 'neat', 'necessarily', 'necessary', 'neck', 'need',
    'negative', 'negotiate', 'negotiation', 'neighbor', 'neighborhood',
    'neither', 'nerve', 'nervous', 'nest', 'net', 'network', 'neutral',
    'never', 'nevertheless', 'new', 'newly', 'news', 'newspaper', 'next',
    'nice', 'night', 'nine', 'no', 'nobody', 'nod', 'noise', 'none',
    'nonetheless', 'nor', 'normal', 'normally', 'north', 'northern',
    'nose', 'not', 'notable', 'note', 'nothing', 'notice', 'notion',
    'novel', 'november', 'now', 'nowhere', 'nuclear', 'number',
    'numerous', 'nurse', 'nut', 'nutrition',
    'nanny', 'napkin', 'narcotic', 'nasty', 'navigate', 'navigation',
    'neglect', 'negligence', 'neutral', 'niche', 'nightmare', 'nimble',
    'nitrogen', 'noble', 'nocturnal', 'nomad', 'nominal', 'nominate',
    'nonsense', 'noodle', 'norm', 'nostalgic', 'notch', 'noteworthy',
    'notify', 'notorious', 'nourish', 'novelty', 'novice', 'nucleus',
    'nudge', 'nuisance', 'numb', 'nursery', 'nurture',

    # ── O ──
    'oak', 'object', 'objection', 'objective', 'obligation', 'observe',
    'observation', 'observer', 'obstacle', 'obtain', 'obvious',
    'obviously', 'occasion', 'occasionally', 'occupation', 'occupy',
    'occur', 'occurrence', 'ocean', 'october', 'odd', 'odds', 'of',
    'off', 'offense', 'offensive', 'offer', 'office', 'officer',
    'official', 'often', 'oh', 'oil', 'ok', 'okay', 'old', 'olympic',
    'on', 'once', 'one', 'ongoing', 'online', 'only', 'onto', 'open',
    'opening', 'operate', 'operating', 'operation', 'operator', 'opinion',
    'opponent', 'opportunity', 'oppose', 'opposite', 'opposition',
    'option', 'or', 'orange', 'orbit', 'order', 'ordinary', 'organic',
    'organization', 'organize', 'orientation', 'origin', 'original',
    'originally', 'other', 'otherwise', 'ought', 'our', 'ourselves',
    'out', 'outcome', 'outdoor', 'outer', 'output', 'outside',
    'outstanding', 'over', 'overall', 'overcome', 'overlook', 'overseas',
    'overwhelming', 'owe', 'own', 'owner', 'ownership', 'oxygen',
    'oath', 'oasis', 'obedient', 'obey', 'oblige', 'obscure', 'obsess',
    'obsolete', 'obstruct', 'occupant', 'octopus', 'odor', 'offend',
    'offspring', 'olive', 'omen', 'omit', 'onset', 'opaque', 'opera',
    'optical', 'optimal', 'optimism', 'optimistic', 'optimize', 'oracle',
    'oral', 'orbital', 'orchard', 'orchestra', 'ordeal', 'ore',
    'orient', 'ornament', 'orphan', 'orthodox', 'oscillate', 'ounce',
    'outbreak', 'outcast', 'outdoors', 'outfit', 'outlaw', 'outline',
    'outlook', 'outrage', 'outreach', 'outskirts', 'outward', 'oval',
    'oven', 'overall', 'overflow', 'overhead', 'overlap', 'overturn',
    'overwhelm', 'owl', 'oyster',

    # ── P ──
    'pace', 'pack', 'package', 'pad', 'page', 'paid', 'pain', 'painful',
    'paint', 'painter', 'painting', 'pair', 'palace', 'pale', 'palm',
    'pan', 'panel', 'panic', 'paper', 'paradigm', 'paragraph', 'parallel',
    'parent', 'park', 'parking', 'part', 'partially', 'participant',
    'participate', 'participation', 'particular', 'particularly',
    'partly', 'partner', 'partnership', 'party', 'pass', 'passage',
    'passenger', 'passion', 'passionate', 'passive', 'past', 'patch',
    'path', 'patience', 'patient', 'pattern', 'pause', 'pay', 'payment',
    'peace', 'peaceful', 'peak', 'peer', 'penalty', 'pension', 'people',
    'pepper', 'per', 'perceive', 'percent', 'percentage', 'perception',
    'perfect', 'perfectly', 'perform', 'performance', 'perhaps', 'period',
    'permanent', 'permission', 'permit', 'person', 'personal',
    'personality', 'personally', 'personnel', 'perspective', 'persuade',
    'pet', 'phase', 'phenomenon', 'philosophy', 'phone', 'photo',
    'photograph', 'photographer', 'photography', 'phrase', 'physical',
    'physically', 'physician', 'physics', 'piano', 'pick', 'picture',
    'pie', 'piece', 'pig', 'pile', 'pilot', 'pin', 'pine', 'pink',
    'pioneer', 'pipe', 'pitch', 'pizza', 'place', 'plain', 'plan',
    'plane', 'planet', 'planning', 'plant', 'plastic', 'plate',
    'platform', 'play', 'player', 'please', 'pleasure', 'plenty',
    'plot', 'plug', 'plus', 'pocket', 'poem', 'poet', 'poetry', 'point',
    'pole', 'police', 'policeman', 'policy', 'political', 'politically',
    'politician', 'politics', 'poll', 'pollution', 'pond', 'pool', 'poor',
    'pop', 'popular', 'popularity', 'population', 'porch', 'port',
    'portion', 'portrait', 'portray', 'pose', 'position', 'positive',
    'possess', 'possession', 'possibility', 'possible', 'possibly',
    'post', 'pot', 'potato', 'potential', 'potentially', 'pound', 'pour',
    'poverty', 'powder', 'power', 'powerful', 'practical', 'practice',
    'pray', 'prayer', 'precisely', 'predict', 'prediction', 'prefer',
    'preference', 'pregnancy', 'pregnant', 'prejudice', 'premier',
    'premise', 'premium', 'preparation', 'prepare', 'prepared',
    'prescription', 'presence', 'present', 'presentation', 'preserve',
    'presidency', 'president', 'presidential', 'press', 'pressure',
    'presumably', 'pretty', 'prevent', 'previous', 'previously', 'price',
    'pride', 'priest', 'primarily', 'primary', 'prime', 'prince',
    'princess', 'principal', 'principle', 'print', 'prior', 'priority',
    'prison', 'prisoner', 'privacy', 'private', 'privilege', 'prize',
    'probably', 'problem', 'procedure', 'proceed', 'process',
    'processing', 'produce', 'producer', 'product', 'production',
    'profession', 'professional', 'professor', 'profile', 'profit',
    'program', 'progress', 'project', 'prominent', 'promise', 'promote',
    'promotion', 'prompt', 'proof', 'proper', 'properly', 'property',
    'proportion', 'proposal', 'propose', 'proposed', 'prosecutor',
    'prospect', 'protect', 'protection', 'protein', 'protest',
    'protestant', 'proud', 'prove', 'provide', 'provider', 'province',
    'provision', 'provoke', 'psychological', 'psychologist', 'psychology',
    'public', 'publication', 'publicly', 'publish', 'publisher', 'pull',
    'pump', 'punch', 'punishment', 'pupil', 'purchase', 'pure', 'purple',
    'purpose', 'pursue', 'push', 'put',
    'pacific', 'paddle', 'pagan', 'palace', 'pamphlet', 'pancake',
    'panorama', 'parachute', 'parade', 'paradise', 'paradox', 'parameter',
    'parcel', 'pardon', 'parish', 'parliament', 'parrot', 'partial',
    'particle', 'partition', 'passport', 'pasture', 'patriot', 'patrol',
    'patron', 'pavilion', 'pave', 'pavement', 'paw', 'peanut', 'pearl',
    'peasant', 'peculiar', 'pedagogy', 'pedal', 'pedestrian', 'peel',
    'peninsula', 'penny', 'perceive', 'perch', 'peril', 'periodic',
    'peripheral', 'perish', 'perk', 'perpetual', 'perplex', 'persecute',
    'persist', 'persistent', 'persona', 'petition', 'petroleum',
    'phantom', 'pharmaceutical', 'pharmacy', 'phoenix', 'phosphorus',
    'photon', 'physician', 'pigeon', 'pilgrim', 'pillar', 'pillow',
    'pinch', 'pint', 'pious', 'pipeline', 'pirate', 'pistol', 'pit',
    'pixel', 'plague', 'plank', 'plantation', 'plaster', 'plateau',
    'plausible', 'plaza', 'plea', 'plead', 'pledge', 'plenary', 'pluck',
    'plumbing', 'plume', 'plunge', 'plywood', 'pneumonia', 'podium',
    'poker', 'polar', 'polite', 'polygon', 'pompous', 'ponder',
    'porcelain', 'pork', 'portable', 'portfolio', 'postal', 'postpone',
    'posture', 'potent', 'pottery', 'poultry', 'prairie', 'preach',
    'precaution', 'precede', 'precious', 'precise', 'precision',
    'predator', 'predecessor', 'predicament', 'predominant', 'preface',
    'preliminary', 'premature', 'premise', 'premium', 'prestige',
    'prevail', 'prevalent', 'prey', 'priceless', 'primitive', 'privilege',
    'probe', 'procession', 'proclaim', 'prodigy', 'productive',
    'proficiency', 'profound', 'prohibition', 'projection', 'prolific',
    'prolonged', 'promenade', 'prone', 'pronounce', 'propaganda',
    'propel', 'prophet', 'prose', 'prosperity', 'prosperous',
    'protagonist', 'protocol', 'prototype', 'provenance', 'proverb',
    'providence', 'provoke', 'prowl', 'proximity', 'prudent', 'psalm',
    'pub', 'pudding', 'pulse', 'pumpkin', 'punctual', 'punish', 'puppy',
    'puzzle', 'pyramid',

    # ── Q ──
    'qualification', 'qualify', 'quality', 'quantity', 'quarter',
    'quarterback', 'queen', 'question', 'quick', 'quickly', 'quiet',
    'quietly', 'quit', 'quite', 'quiz', 'quota', 'quote',
    'quake', 'quarantine', 'quarrel', 'quarry', 'quart', 'quest',
    'questionnaire', 'queue', 'quilt', 'quirky', 'quorum',

    # ── R ──
    'race', 'racial', 'racism', 'rack', 'radar', 'radiation', 'radical',
    'radio', 'rage', 'raid', 'rail', 'rain', 'raise', 'range', 'rank',
    'rapid', 'rapidly', 'rare', 'rarely', 'rat', 'rate', 'rather',
    'ratio', 'raw', 'reach', 'react', 'reaction', 'read', 'reader',
    'reading', 'ready', 'real', 'realistic', 'reality', 'realize',
    'really', 'realm', 'rear', 'reason', 'reasonable', 'rebel',
    'rebuild', 'recall', 'receive', 'recent', 'recently', 'reception',
    'recipe', 'recipient', 'recognition', 'recognize', 'recommend',
    'recommendation', 'record', 'recording', 'recover', 'recovery',
    'recruit', 'red', 'reduce', 'reduction', 'refer', 'reference',
    'reflect', 'reflection', 'reform', 'refrigerator', 'refugee',
    'refuse', 'regard', 'regarding', 'regime', 'region', 'regional',
    'register', 'regular', 'regularly', 'regulate', 'regulation',
    'reinforce', 'reject', 'relate', 'relation', 'relationship',
    'relative', 'relatively', 'relax', 'release', 'relevant', 'relief',
    'religion', 'religious', 'reluctant', 'rely', 'remain', 'remaining',
    'remark', 'remarkable', 'remedy', 'remember', 'remind', 'remote',
    'removal', 'remove', 'renaissance', 'render', 'renew', 'rent',
    'repair', 'repeat', 'repeatedly', 'replace', 'replacement', 'reply',
    'report', 'reporter', 'represent', 'representation', 'representative',
    'reproduce', 'republic', 'republican', 'reputation', 'request',
    'require', 'requirement', 'rescue', 'research', 'researcher',
    'resemble', 'reservation', 'reserve', 'resident', 'residential',
    'resign', 'resist', 'resistance', 'resolution', 'resolve', 'resort',
    'resource', 'respond', 'response', 'responsibility', 'responsible',
    'rest', 'restaurant', 'restore', 'restriction', 'result', 'retain',
    'retire', 'retirement', 'retreat', 'return', 'reveal', 'revenue',
    'review', 'revolution', 'revolutionary', 'reward', 'rhetoric',
    'rhythm', 'rice', 'rich', 'rid', 'ride', 'rider', 'ridge', 'rifle',
    'right', 'ring', 'riot', 'rise', 'rising', 'risk', 'river', 'road',
    'robot', 'rock', 'rocket', 'rod', 'role', 'roll', 'roman', 'romance',
    'romantic', 'roof', 'room', 'root', 'rope', 'rose', 'rotate', 'rough',
    'roughly', 'round', 'route', 'routine', 'row', 'royal', 'rub',
    'ruin', 'rule', 'ruler', 'ruling', 'run', 'running', 'rural', 'rush',
    'rabbit', 'rack', 'radiant', 'radius', 'raft', 'rainbow', 'rally',
    'ranch', 'random', 'ranger', 'ransom', 'rascal', 'rash', 'raspberry',
    'rattle', 'raven', 'razor', 'realm', 'reap', 'rebellion', 'rebound',
    'recede', 'recess', 'recital', 'reckon', 'reclaim', 'recollect',
    'reconcile', 'rectangle', 'rectify', 'recur', 'redeem', 'redundant',
    'reed', 'reef', 'referee', 'refine', 'refuge', 'refund', 'regal',
    'regiment', 'rehearsal', 'reign', 'rein', 'relic', 'relish',
    'relocate', 'reluctance', 'remainder', 'remnant', 'remodel',
    'remorse', 'renovate', 'renowned', 'rental', 'repay', 'repeal',
    'repel', 'repent', 'replica', 'repress', 'reprise', 'reproach',
    'reptile', 'reputable', 'resent', 'reservoir', 'reside', 'residue',
    'resilient', 'resin', 'resolute', 'resonance', 'restless',
    'restrain', 'resume', 'resurrect', 'retail', 'retaliate', 'retention',
    'retort', 'retrieve', 'retrospect', 'reunion', 'revelation',
    'revenge', 'reversal', 'reverse', 'revise', 'revision', 'revival',
    'revive', 'revolt', 'rhyme', 'ribbon', 'righteous', 'rigid',
    'rigorous', 'rim', 'rinse', 'ripple', 'ritual', 'rival', 'roar',
    'robe', 'robin', 'robust', 'rogue', 'rookie', 'roster', 'rotation',
    'rouge', 'roundabout', 'royalty', 'rubble', 'ruby', 'rudimentary',
    'rug', 'rumble', 'rumor', 'rupture', 'rustic', 'ruthless', 'rye',

    # ── S ──
    'sacred', 'sacrifice', 'sad', 'sadly', 'safe', 'safety', 'sail',
    'saint', 'sake', 'salad', 'salary', 'sale', 'salt', 'same', 'sample',
    'sanction', 'sand', 'sandwich', 'satellite', 'satisfaction',
    'satisfy', 'saturday', 'sauce', 'save', 'saving', 'say', 'scale',
    'scandal', 'scare', 'scenario', 'scene', 'schedule', 'scheme',
    'scholar', 'scholarship', 'school', 'science', 'scientific',
    'scientist', 'scope', 'score', 'scream', 'screen', 'script', 'sea',
    'search', 'season', 'seat', 'second', 'secondary', 'secret',
    'secretary', 'section', 'sector', 'secular', 'secure', 'security',
    'see', 'seed', 'seek', 'seem', 'segment', 'seize', 'select',
    'selection', 'self', 'sell', 'senate', 'senator', 'send', 'senior',
    'sense', 'sensitive', 'sensitivity', 'sentence', 'separate',
    'sequence', 'series', 'serious', 'seriously', 'serve', 'server',
    'service', 'session', 'set', 'setting', 'settle', 'settlement',
    'seven', 'several', 'severe', 'sex', 'sexual', 'shade', 'shadow',
    'shake', 'shall', 'shame', 'shape', 'share', 'sharp', 'she',
    'shed', 'sheer', 'sheet', 'shelf', 'shell', 'shelter', 'shift',
    'shine', 'ship', 'shirt', 'shock', 'shoe', 'shoot', 'shooting',
    'shop', 'shopping', 'shore', 'short', 'shortage', 'shortly',
    'shot', 'should', 'shoulder', 'shout', 'show', 'shower', 'shut',
    'sick', 'side', 'sight', 'sign', 'signal', 'signature', 'significance',
    'significant', 'significantly', 'silence', 'silent', 'silly',
    'silver', 'similar', 'similarly', 'simple', 'simply', 'sin', 'since',
    'sing', 'singer', 'single', 'sink', 'sir', 'sister', 'sit', 'site',
    'situation', 'six', 'size', 'ski', 'skill', 'skin', 'sky', 'slave',
    'slavery', 'sleep', 'slice', 'slide', 'slight', 'slightly', 'slim',
    'slip', 'slope', 'slow', 'slowly', 'small', 'smart', 'smell',
    'smile', 'smoke', 'smooth', 'snap', 'snow', 'so', 'soccer', 'social',
    'society', 'soft', 'software', 'soil', 'solar', 'soldier', 'solid',
    'solution', 'solve', 'some', 'somebody', 'someday', 'somehow',
    'someone', 'something', 'sometimes', 'somewhat', 'somewhere', 'son',
    'song', 'soon', 'sophisticated', 'sorry', 'sort', 'soul', 'sound',
    'source', 'south', 'southern', 'space', 'speak', 'speaker',
    'special', 'specialist', 'specially', 'specific', 'specifically',
    'spectrum', 'speech', 'speed', 'spell', 'spend', 'spending',
    'sphere', 'spin', 'spirit', 'spiritual', 'split', 'spokesman',
    'sponsor', 'sport', 'spot', 'spread', 'spring', 'spy', 'squad',
    'square', 'squeeze', 'stability', 'stable', 'staff', 'stage',
    'stair', 'stake', 'stand', 'standard', 'standing', 'star', 'stare',
    'start', 'starting', 'state', 'statement', 'station', 'status',
    'statute', 'stay', 'steady', 'steal', 'steam', 'steel', 'steep',
    'steer', 'stem', 'step', 'stereotype', 'stick', 'stiff', 'still',
    'stimulate', 'stimulus', 'stir', 'stock', 'stomach', 'stone', 'stop',
    'store', 'storm', 'story', 'straight', 'strange', 'stranger',
    'strategic', 'strategy', 'stream', 'street', 'strength', 'strengthen',
    'stress', 'stretch', 'strict', 'strictly', 'strike', 'string',
    'strip', 'stroke', 'strong', 'strongly', 'structure', 'struggle',
    'student', 'studio', 'study', 'stuff', 'stupid', 'style', 'subject',
    'submit', 'subsequent', 'substance', 'substantial', 'subtle',
    'suburb', 'suburban', 'succeed', 'success', 'successful',
    'successfully', 'such', 'sudden', 'suddenly', 'sue', 'suffer',
    'sufficient', 'sugar', 'suggest', 'suggestion', 'suicide', 'suit',
    'suitable', 'summer', 'summit', 'sun', 'sunday', 'super', 'superior',
    'supplement', 'supplier', 'supply', 'support', 'supporter', 'suppose',
    'supposed', 'supreme', 'sure', 'surely', 'surface', 'surgery',
    'surprise', 'surprised', 'surprising', 'surprisingly', 'surround',
    'surrounding', 'survey', 'survival', 'survive', 'survivor',
    'suspect', 'suspend', 'suspicion', 'suspicious', 'sustain', 'swallow',
    'swamp', 'swap', 'swear', 'sweep', 'sweet', 'swim', 'swing',
    'switch', 'symbol', 'sympathy', 'symptom', 'syndrome', 'system',
    'sabotage', 'sack', 'safari', 'safeguard', 'sage', 'salmon',
    'salon', 'salute', 'salvation', 'sanctuary', 'sanity', 'sapphire',
    'sardine', 'savage', 'scaffold', 'scalar', 'scalpel', 'scandal',
    'scarce', 'scaffold', 'scatter', 'scenic', 'scent', 'scepter',
    'scholar', 'scissors', 'scold', 'scooter', 'scorch', 'scorpion',
    'scout', 'scramble', 'scrap', 'scratch', 'scroll', 'scrub',
    'scrutiny', 'sculpture', 'seal', 'seamless', 'seasonal', 'seclude',
    'sect', 'sedan', 'sediment', 'segregate', 'selenium', 'semester',
    'seminar', 'sensation', 'sentiment', 'sentimental', 'sequel',
    'serene', 'sermon', 'serpent', 'serum', 'setback', 'severe',
    'sew', 'shaft', 'shallow', 'shatter', 'shave', 'shepherd',
    'shield', 'shimmer', 'shipment', 'shortage', 'shrine', 'shrink',
    'shrub', 'shudder', 'shuffle', 'sibling', 'siege', 'sieve',
    'silhouette', 'silicon', 'silk', 'silly', 'simulate', 'simultaneous',
    'sincere', 'siren', 'skeleton', 'sketch', 'skeptic', 'slab',
    'slap', 'slaughter', 'slender', 'slogan', 'slot', 'slum', 'smash',
    'snack', 'snail', 'snake', 'sneeze', 'sniper', 'snippet', 'soak',
    'soar', 'sober', 'socket', 'sodium', 'sofa', 'solar', 'sole',
    'solemn', 'solidarity', 'solitary', 'solo', 'somber', 'sonic',
    'soothe', 'soprano', 'sovereign', 'sow', 'spa', 'spacecraft',
    'span', 'spare', 'spark', 'spatial', 'spawn', 'spear', 'specimen',
    'spectacle', 'spectacular', 'speculate', 'speedy', 'spider',
    'spill', 'spine', 'spiral', 'splendid', 'splinter', 'spoke',
    'spontaneous', 'spoon', 'spotlight', 'spouse', 'sprinkle', 'spur',
    'squadron', 'stagger', 'stagnant', 'stain', 'stalk', 'stall',
    'stamina', 'stampede', 'stance', 'standpoint', 'staple', 'starve',
    'stash', 'static', 'stationary', 'statistic', 'statistical',
    'statue', 'stature', 'steadfast', 'steak', 'stellar', 'stereo',
    'stern', 'steward', 'sticker', 'stimulus', 'sting', 'stitch',
    'stockpile', 'stool', 'storage', 'strand', 'strap', 'straw',
    'stray', 'stride', 'strife', 'striking', 'stripe', 'strive',
    'sturdy', 'stump', 'stun', 'stunt', 'stumble', 'sublime',
    'submarine', 'submission', 'subordinate', 'subscribe', 'subsidiary',
    'subsidy', 'substitute', 'subtract', 'suburban', 'succession',
    'successor', 'suction', 'suffix', 'sulfur', 'sultan', 'summon',
    'sunlight', 'sunrise', 'sunset', 'sunshine', 'superb',
    'superficial', 'superintendent', 'supervise', 'supper', 'surge',
    'surgeon', 'surplus', 'surrender', 'surveillance', 'susceptible',
    'suspension', 'sustenance', 'swan', 'sword', 'syllable', 'symbolic',
    'symmetry', 'synagogue', 'synthesis', 'synthetic', 'syrup',
    'systematic',

    # ── T ──
    'table', 'tablet', 'tactic', 'tail', 'take', 'tale', 'talent',
    'talk', 'tall', 'tank', 'tap', 'tape', 'target', 'task', 'taste',
    'tax', 'taxpayer', 'tea', 'teach', 'teacher', 'teaching', 'team',
    'tear', 'technical', 'technically', 'technique', 'technology', 'teen',
    'teenager', 'telephone', 'television', 'tell', 'temperature',
    'temporary', 'ten', 'tend', 'tendency', 'tender', 'tennis',
    'tension', 'tent', 'term', 'terms', 'terrible', 'territory',
    'terror', 'terrorism', 'terrorist', 'test', 'testament', 'testify',
    'testimony', 'testing', 'text', 'than', 'thank', 'thanks',
    'thanksgiving', 'that', 'the', 'theater', 'their', 'them', 'theme',
    'themselves', 'then', 'theory', 'therapy', 'there', 'therefore',
    'these', 'they', 'thick', 'thin', 'thing', 'think', 'thinking',
    'third', 'thirteen', 'thirty', 'this', 'thorough', 'thoroughly',
    'those', 'though', 'thought', 'thousand', 'threat', 'threaten',
    'three', 'throat', 'through', 'throughout', 'throw', 'thus', 'ticket',
    'tide', 'tie', 'tight', 'till', 'timber', 'time', 'timeline',
    'tiny', 'tip', 'tire', 'tired', 'tissue', 'title', 'to', 'tobacco',
    'today', 'toe', 'together', 'tolerance', 'toll', 'tomato',
    'tomorrow', 'tone', 'tongue', 'tonight', 'too', 'tool', 'tooth',
    'top', 'topic', 'torture', 'toss', 'total', 'totally', 'touch',
    'tough', 'tour', 'tourist', 'tournament', 'toward', 'towards',
    'tower', 'town', 'toy', 'trace', 'track', 'trade', 'tradition',
    'traditional', 'traffic', 'tragedy', 'trail', 'train', 'training',
    'trait', 'transfer', 'transform', 'transformation', 'transition',
    'translate', 'transmission', 'transport', 'transportation', 'trap',
    'trash', 'travel', 'treat', 'treatment', 'treaty', 'tree', 'trend',
    'trial', 'tribe', 'trick', 'trigger', 'trim', 'trio', 'trip',
    'triumph', 'troop', 'tropical', 'trouble', 'truck', 'true', 'truly',
    'trust', 'truth', 'try', 'tube', 'tuesday', 'tumor', 'tune',
    'tunnel', 'turn', 'twelve', 'twenty', 'twice', 'twin', 'twist',
    'two', 'type', 'typical', 'typically',
    'tableau', 'taboo', 'tackle', 'tactical', 'tailor', 'taint',
    'tamper', 'tangible', 'tangle', 'tanker', 'tariff', 'tarnish',
    'tattoo', 'tease', 'tedious', 'telescope', 'temper', 'temperament',
    'temple', 'temporal', 'tempt', 'tenacious', 'tenant', 'tenure',
    'terminal', 'terminate', 'terrain', 'terrace', 'terrific',
    'terrify', 'testament', 'textile', 'texture', 'thankful', 'thatch',
    'theatrical', 'theft', 'thematic', 'theorem', 'therapeutic',
    'thermal', 'thesis', 'threshold', 'thrill', 'thrive', 'throne',
    'throttle', 'thunder', 'tidal', 'tighten', 'tile', 'tilt',
    'timid', 'tingle', 'titanium', 'toast', 'token', 'tolerate',
    'tomb', 'topple', 'torch', 'torment', 'tornado', 'torpedo',
    'torrent', 'toxic', 'tract', 'trademark', 'trajectory', 'trample',
    'tranquil', 'transaction', 'transcend', 'transcript', 'transit',
    'transmit', 'transparent', 'transplant', 'trauma', 'traverse',
    'treason', 'treasure', 'tremendous', 'trench', 'trespass',
    'triangle', 'tribunal', 'tribute', 'trifle', 'trilogy', 'trinity',
    'tripod', 'trivial', 'trophy', 'truce', 'trumpet', 'trustworthy',
    'tsunami', 'tuition', 'tulip', 'tumble', 'turbine', 'turbulent',
    'turf', 'turmoil', 'turnover', 'turquoise', 'turtle', 'tutor',
    'twilight', 'twinkle', 'typhoon', 'tyranny',

    # ── U ──
    'ugly', 'ultimate', 'ultimately', 'umbrella', 'unable', 'uncle',
    'under', 'undergo', 'underlying', 'undermine', 'understand',
    'understanding', 'unemployment', 'unfair', 'unfortunately', 'unhappy',
    'uniform', 'union', 'unique', 'unit', 'unite', 'unity', 'universal',
    'universe', 'university', 'unknown', 'unless', 'unlike', 'unlikely',
    'until', 'unusual', 'up', 'upon', 'upper', 'upset', 'upstairs',
    'urban', 'urge', 'urgent', 'us', 'use', 'used', 'useful', 'user',
    'usual', 'usually', 'utility', 'utilize',
    'ubiquitous', 'ulterior', 'ultra', 'unanimous', 'unaware',
    'uncertain', 'uncommon', 'uncover', 'underdog', 'underestimate',
    'undergo', 'undergraduate', 'underground', 'underscore', 'undertake',
    'underway', 'undue', 'unfold', 'unify', 'unilateral', 'unintended',
    'unison', 'unleash', 'unlock', 'unmask', 'unprecedented', 'unravel',
    'unrest', 'unsettled', 'unveil', 'unwilling', 'upbeat', 'update',
    'upgrade', 'uphold', 'upkeep', 'uplift', 'uprising', 'uproar',
    'uproot', 'upstream', 'uptake', 'uranium', 'usher', 'utensil',
    'utter', 'utterance',

    # ── V ──
    'vacation', 'vaccine', 'valley', 'valuable', 'value', 'van',
    'variable', 'variation', 'variety', 'various', 'vary', 'vast',
    'vehicle', 'venture', 'venue', 'verb', 'verdict', 'version',
    'versus', 'very', 'vessel', 'veteran', 'via', 'victim', 'victory',
    'video', 'view', 'viewer', 'village', 'violate', 'violation',
    'violence', 'violent', 'virtual', 'virtually', 'virtue', 'virus',
    'visibility', 'visible', 'vision', 'visit', 'visitor', 'visual',
    'vital', 'vocabulary', 'voice', 'volume', 'voluntary', 'volunteer',
    'vote', 'voter', 'vulnerable',
    'vacuum', 'vague', 'vain', 'valiant', 'valid', 'validate', 'valor',
    'vampire', 'vandal', 'vanguard', 'vanilla', 'vanish', 'vanity',
    'vapor', 'varnish', 'vault', 'vegetation', 'veil', 'vein', 'velvet',
    'vendor', 'vengeance', 'venom', 'vent', 'verbal', 'verge', 'verify',
    'versatile', 'verse', 'vertical', 'vest', 'veterinary', 'veto',
    'viable', 'vibrant', 'vibrate', 'vicious', 'vigilant', 'vigor',
    'villain', 'vindicate', 'vine', 'vineyard', 'vintage', 'vinyl',
    'violet', 'virgin', 'visceral', 'vivid', 'vocal', 'vocation',
    'void', 'volatile', 'volcano', 'volleyball', 'voltage', 'voluntary',
    'vow', 'voyage', 'vulgar', 'vulture',

    # ── W ──
    'wage', 'wait', 'wake', 'walk', 'wall', 'wander', 'want', 'war',
    'warm', 'warn', 'warning', 'wash', 'waste', 'watch', 'water', 'wave',
    'way', 'we', 'weak', 'weakness', 'wealth', 'wealthy', 'weapon',
    'wear', 'weather', 'web', 'website', 'wedding', 'wednesday', 'week',
    'weekend', 'weekly', 'weigh', 'weight', 'weird', 'welcome',
    'welfare', 'well', 'west', 'western', 'wet', 'what', 'whatever',
    'wheat', 'wheel', 'when', 'whenever', 'where', 'whereas', 'wherever',
    'whether', 'which', 'while', 'whisper', 'white', 'who', 'whoever',
    'whole', 'whom', 'whose', 'why', 'wide', 'widely', 'widespread',
    'wife', 'wild', 'will', 'willing', 'willingness', 'win', 'wind',
    'window', 'wine', 'wing', 'winner', 'winter', 'wire', 'wisdom',
    'wise', 'wish', 'with', 'withdraw', 'withdrawal', 'within',
    'without', 'witness', 'woman', 'women', 'wonder', 'wonderful',
    'wood', 'wooden', 'wool', 'word', 'work', 'worker', 'workforce',
    'working', 'workplace', 'workshop', 'world', 'worried', 'worry',
    'worse', 'worship', 'worst', 'worth', 'worthy', 'would', 'wound',
    'wrap', 'write', 'writer', 'writing', 'wrong',
    'wade', 'waffle', 'wagon', 'waist', 'wallet', 'walnut', 'ward',
    'wardrobe', 'warehouse', 'warfare', 'warrant', 'warrior', 'wary',
    'waterfall', 'watt', 'wax', 'weaken', 'weasel', 'weave', 'wedge',
    'weed', 'welfare', 'whale', 'wharf', 'whistle', 'wholesale',
    'wholesome', 'wicked', 'widget', 'widow', 'width', 'wield',
    'wilderness', 'wildlife', 'willow', 'wilt', 'wince', 'windmill',
    'wingspan', 'wipe', 'witch', 'withhold', 'withstand', 'wolf',
    'wolverine', 'womb', 'woodland', 'workload', 'worm', 'worsen',
    'worthwhile', 'wrangle', 'wrath', 'wreath', 'wreck', 'wrestle',
    'wring', 'wrinkle', 'wrist',

    # ── X ──
    'xenophobia', 'xerox',

    # ── Y ──
    'yard', 'yeah', 'year', 'yell', 'yellow', 'yes', 'yesterday', 'yet',
    'yield', 'you', 'young', 'youngster', 'your', 'yours', 'yourself',
    'youth',
    'yacht', 'yearn', 'yeast', 'yoga', 'yoke',

    # ── Z ──
    'zeal', 'zealous', 'zero', 'zone', 'zoo',
    'zenith', 'zephyr', 'zigzag', 'zinc', 'zodiac', 'zombie',
})

# Hinglish dictionary removed per user request for strict English (India)

# ═══════════════════════════════════════════════════════════════════════════════
#  WordValidator — the brain of the spelling engine
# ═══════════════════════════════════════════════════════════════════════════════
class WordValidator:
    """
    Provides three-layer spelling intelligence:
      1. Dictionary lookup + Offline pyspellchecker (120k words) + Windows COM Spell Checker
      2. Local Norvig-style edit-distance spell checker (Edit-Distance 1 ONLY for bulletproof precision)
      3. Post-API correction validation (Levenshtein guards)
    """

    def __init__(self):
        self._known_good: set[str] = set()  # Dynamic cache — grows as user types
        self._lock = threading.Lock()
        
        # Initialize high-performance offline pyspellchecker (120,000+ words)
        self._offline_spell = None
        try:
            from spellchecker import SpellChecker
            # Distance=1 for speed and maximum word-boundary safety
            self._offline_spell = SpellChecker(distance=1)
        except Exception:
            pass
        
        # Initialize native Windows Spell Checker COM API as secondary local verification
        self._win_checker = None
        try:
            import win32com.client
            import pythoncom
            pythoncom.CoInitialize()
            factory = win32com.client.Dispatch("SpellCheckerFactory")
            if factory:
                # Force English (India) per user request
                for lang in ["en-IN", "en-GB", "en-US", "en", "en-AU", "en-CA"]:
                    try:
                        if factory.IsSupported(lang):
                            self._win_checker = factory.CreateSpellChecker(lang)
                            break
                    except Exception:
                        pass
        except Exception:
            pass

    # ── Layer 1: Is the word already valid? ──────────────────────────────────────
    def is_valid_word(self, word: str) -> bool:
        """
        Returns True if the word is a known valid English or Hinglish word.
        Uses static dictionaries, dynamic known-good cache, offline pyspellchecker, and Windows COM Spell Checker.
        """
        w = word.lower().strip()
        if not w:
            return False
        if w in _COMMON_ENGLISH:
            return True
        with self._lock:
            if w in self._known_good:
                return True

        # Use high-performance offline pyspellchecker (120,000+ words)
        if self._offline_spell:
            try:
                if w in self._offline_spell:
                    with self._lock:
                        self._known_good.add(w)
                    return True
            except Exception:
                pass

        # Use native Windows Spell Checker as fallback
        if self._win_checker:
            try:
                import pythoncom
                pythoncom.CoInitialize()
                errors = self._win_checker.Check(word)
                has_errors = False
                if errors:
                    err = errors.Next()
                    if err:
                        has_errors = True
                if not has_errors:
                    with self._lock:
                        self._known_good.add(w)
                    return True
            except Exception:
                pass

        return False

    def mark_known_good(self, word: str):
        """
        Add a word to the dynamic known-good cache.
        Called when the API returns the word unchanged — meaning it's valid.
        """
        w = word.lower().strip()
        if w and len(w) >= 3:
            with self._lock:
                self._known_good.add(w)

    # ── Layer 2: Local edit-distance spell correction ────────────────────────────
    def find_local_correction(self, word: str) -> str | None:
        """
        Try to find a correction using pyspellchecker's built-in correction()
        method, which uses precomputed word-frequency tables for fast,
        accurate corrections.

        Falls back to static dictionary edit-distance if pyspellchecker
        is not available.

        Guards:
          - First letter must match (typos almost never change first letter)
          - Edit distance must be ≤ 2
          - Correction must be a real word
        """
        w = word.lower().strip()
        if not w:
            return None

        # ── Primary: Use pyspellchecker's optimized correction ──────────────
        if self._offline_spell:
            try:
                # correction() returns the most likely correct spelling
                # using word frequency probabilities — fast and accurate
                candidate = self._offline_spell.correction(w)
                if candidate and candidate != w:
                    # Safety guard: first letter must match for words >= 4 chars
                    if len(w) >= 4 and candidate[0] != w[0]:
                        return None
                    # Safety guard: edit distance must be small
                    dist = levenshtein(w, candidate)
                    if dist <= 2:
                        return candidate
            except Exception:
                pass

        # ── Fallback: Check static dictionary with edit distance 1 ──────────
        candidates = []
        for c in self._edits1(w):
            if c in _COMMON_ENGLISH:
                candidates.append(c)
        if candidates:
            # Prefer same first letter
            same_first = [c for c in candidates if c[0] == w[0]]
            if same_first:
                return same_first[0]
            return candidates[0]

        return None

    @staticmethod
    def _edits1(word: str) -> set[str]:
        """Generate all strings that are 1 edit distance away."""
        letters = 'abcdefghijklmnopqrstuvwxyz'
        splits = [(word[:i], word[i:]) for i in range(len(word) + 1)]
        deletes    = [L + R[1:]           for L, R in splits if R]
        transposes = [L + R[1] + R[0] + R[2:] for L, R in splits if len(R) > 1]
        replaces   = [L + c + R[1:]       for L, R in splits if R for c in letters]
        inserts    = [L + c + R           for L, R in splits for c in letters]
        return set(deletes + transposes + replaces + inserts)

    # ── Layer 3: Post-API correction validation ──────────────────────────────────
    def is_valid_correction(self, original: str, corrected: str) -> bool:
        """
        Validate that a correction returned by the API is a genuine spelling
        fix and not a semantic rewrite.

        Guards:
          1. Edit distance must be ≤ ~40% of word length
          2. First letter must match for words ≥ 4 chars
          3. Length must not change drastically
          4. Corrected word must not be in the dictionary if original is too
        """
        if not original or not corrected:
            return False

        o = original.lower().strip()
        c = corrected.lower().strip()

        # Identical = no correction (always valid)
        if o == c:
            return True

        # Guard 1: Edit distance — real typos have small edit distances
        dist = levenshtein(o, c)
        max_allowed = max(2, int(len(o) * 0.45))
        if dist > max_allowed:
            return False

        # Guard 2: First letter anchor — typos almost never change the 1st letter
        # Exception: very short words (3 chars) where transpositions are common
        if len(o) >= 4 and o[0] != c[0]:
            return False

        # Guard 3: Length ratio — correction shouldn't be wildly different length
        len_diff = abs(len(o) - len(c))
        if len_diff > max(2, int(len(o) * 0.4)):
            return False

        # Guard 4: If original is a valid word, reject any change
        # (the API should never "correct" a valid word to something else)
        if self.is_valid_word(original):
            return False

        return True

    # ── Utility ──────────────────────────────────────────────────────────────────
    def get_stats(self) -> dict:
        """Return stats for debugging/UI."""
        with self._lock:
            return {
                'dictionary_size': len(_COMMON_ENGLISH) + len(_COMMON_HINGLISH),
                'known_good_cache': len(self._known_good),
            }
