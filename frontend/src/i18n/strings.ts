/**
 * UI strings.
 *
 * English is the source of truth. A language that lacks a key falls back to
 * English rather than rendering a blank — a missing translation must never
 * produce an empty button.
 *
 * Full translations are provided for the highest-coverage languages. The rest
 * are registered in `languages.ts` and inherit English until reviewed by a
 * native speaker; `translationCoverage()` reports that honestly rather than
 * implying the whole UI is localised.
 */

export type StringKey =
  | 'app.tagline'
  | 'nav.dashboard' | 'nav.spending' | 'nav.safeSpare' | 'nav.roundUps'
  | 'nav.leakRadar' | 'nav.goals' | 'nav.coach' | 'nav.privacy'
  | 'cta.analyze' | 'cta.demo' | 'cta.listen' | 'cta.speak' | 'cta.stop'
  | 'landing.headline' | 'landing.sub'
  | 'voice.title' | 'voice.prompt' | 'voice.listening' | 'voice.unsupported'
  | 'voice.added' | 'voice.example'
  | 'safeSpare.title' | 'safeSpare.now' | 'safeSpare.monthly'
  | 'roundups.potential' | 'roundups.allowed'
  | 'leak.usageQuestion' | 'leak.usageUnknown' | 'leak.notExecuted'
  | 'common.loading' | 'common.error' | 'common.retry' | 'common.cancel'
  | 'common.confirm' | 'common.month' | 'common.year'
  | 'disclaimer.illustrative' | 'disclaimer.noInvest';

type Dict = Partial<Record<StringKey, string>>;

const en: Record<StringKey, string> = {
  'app.tagline': 'Invest only what life can safely spare.',
  'nav.dashboard': 'Dashboard',
  'nav.spending': 'Spending',
  'nav.safeSpare': 'Safe Spare',
  'nav.roundUps': 'Round-ups',
  'nav.leakRadar': 'Leak Radar',
  'nav.goals': 'Goals',
  'nav.coach': 'Coach',
  'nav.privacy': 'Privacy',
  'cta.analyze': 'Analyze my spending',
  'cta.demo': 'Try demo statement',
  'cta.listen': 'Listen',
  'cta.speak': 'Speak your expense',
  'cta.stop': 'Stop',
  'landing.headline': 'Discover what you can safely save—without risking tomorrow’s bills.',
  'landing.sub':
    'Upload a statement or just say what you spent. SafeSpare protects your essential bills first, then shows what is genuinely spare.',
  'voice.title': 'Tell us what you spent',
  'voice.prompt': 'Tap the microphone and say the amount and what it was for.',
  'voice.listening': 'Listening…',
  'voice.unsupported': 'Your browser cannot listen. You can type instead.',
  'voice.added': 'Added',
  'voice.example': 'For example: “I spent 250 rupees on vegetables”',
  'safeSpare.title': 'What your life can safely spare',
  'safeSpare.now': 'Safe Spare right now',
  'safeSpare.monthly': 'Safe monthly contribution',
  'roundups.potential': 'Potential round-ups',
  'roundups.allowed': 'Allowed this month',
  'leak.usageQuestion': 'Have you used this service in the last 30 days?',
  'leak.usageUnknown': 'Until you answer, SafeSpare will not call this unused.',
  'leak.notExecuted': 'SafeSpare has not cancelled anything for you.',
  'common.loading': 'Loading',
  'common.error': 'Something went wrong',
  'common.retry': 'Try again',
  'common.cancel': 'Cancel',
  'common.confirm': 'Confirm',
  'common.month': 'month',
  'common.year': 'year',
  'disclaimer.illustrative':
    'Illustrative only. Actual returns may be higher, lower or negative.',
  'disclaimer.noInvest': 'SafeSpare never invests or moves your money.',
};

const hi: Dict = {
  'app.tagline': 'केवल उतना ही निवेश करें जितना जीवन सुरक्षित रूप से बचा सके।',
  'nav.dashboard': 'डैशबोर्ड', 'nav.spending': 'खर्च', 'nav.safeSpare': 'सुरक्षित बचत',
  'nav.roundUps': 'राउंड-अप', 'nav.leakRadar': 'लीक रडार', 'nav.goals': 'लक्ष्य',
  'nav.coach': 'सहायक', 'nav.privacy': 'गोपनीयता',
  'cta.analyze': 'मेरा खर्च देखें', 'cta.demo': 'नमूना विवरण आज़माएँ',
  'cta.listen': 'सुनें', 'cta.speak': 'अपना खर्च बोलें', 'cta.stop': 'रोकें',
  'landing.headline': 'जानें आप सुरक्षित रूप से कितना बचा सकते हैं—कल के बिलों को जोखिम में डाले बिना।',
  'landing.sub': 'विवरण अपलोड करें या बस बोलें कि आपने क्या खर्च किया। SafeSpare पहले आपके ज़रूरी बिल सुरक्षित रखता है।',
  'voice.title': 'बताइए आपने क्या खर्च किया', 'voice.prompt': 'माइक दबाएँ और राशि तथा कारण बोलें।',
  'voice.listening': 'सुन रहे हैं…', 'voice.unsupported': 'आपका ब्राउज़र सुन नहीं सकता। आप टाइप कर सकते हैं।',
  'voice.added': 'जोड़ा गया', 'voice.example': 'जैसे: “मैंने सब्ज़ी पर 250 रुपये खर्च किए”',
  'safeSpare.title': 'आपका जीवन सुरक्षित रूप से कितना बचा सकता है',
  'safeSpare.now': 'अभी सुरक्षित बचत', 'safeSpare.monthly': 'सुरक्षित मासिक योगदान',
  'roundups.potential': 'संभावित राउंड-अप', 'roundups.allowed': 'इस माह अनुमत',
  'leak.usageQuestion': 'क्या आपने पिछले 30 दिनों में यह सेवा इस्तेमाल की?',
  'leak.usageUnknown': 'जब तक आप उत्तर नहीं देते, SafeSpare इसे अप्रयुक्त नहीं कहेगा।',
  'leak.notExecuted': 'SafeSpare ने आपकी ओर से कुछ भी रद्द नहीं किया है।',
  'common.loading': 'लोड हो रहा है', 'common.error': 'कुछ गड़बड़ हुई', 'common.retry': 'फिर कोशिश करें',
  'common.cancel': 'रद्द करें', 'common.confirm': 'पुष्टि करें', 'common.month': 'माह', 'common.year': 'वर्ष',
  'disclaimer.illustrative': 'केवल उदाहरण। वास्तविक प्रतिफल अधिक, कम या ऋणात्मक हो सकता है।',
  'disclaimer.noInvest': 'SafeSpare कभी आपका पैसा निवेश या स्थानांतरित नहीं करता।',
};

const bn: Dict = {
  'app.tagline': 'জীবন যতটা নিরাপদে ছাড়তে পারে, কেবল ততটাই বিনিয়োগ করুন।',
  'nav.dashboard': 'ড্যাশবোর্ড', 'nav.spending': 'খরচ', 'nav.safeSpare': 'নিরাপদ সঞ্চয়',
  'nav.roundUps': 'রাউন্ড-আপ', 'nav.leakRadar': 'লিক রাডার', 'nav.goals': 'লক্ষ্য',
  'nav.coach': 'সহায়ক', 'nav.privacy': 'গোপনীয়তা',
  'cta.analyze': 'আমার খরচ দেখুন', 'cta.demo': 'নমুনা বিবরণী দেখুন',
  'cta.listen': 'শুনুন', 'cta.speak': 'আপনার খরচ বলুন', 'cta.stop': 'থামুন',
  'landing.headline': 'জানুন আপনি নিরাপদে কতটা সঞ্চয় করতে পারেন—আগামীকালের বিল ঝুঁকিতে না ফেলে।',
  'voice.title': 'বলুন আপনি কী খরচ করেছেন', 'voice.prompt': 'মাইক চাপুন এবং পরিমাণ ও কারণ বলুন।',
  'voice.listening': 'শুনছি…', 'voice.added': 'যোগ করা হয়েছে',
  'voice.example': 'যেমন: “আমি সবজিতে ২৫০ টাকা খরচ করেছি”',
  'safeSpare.now': 'এখন নিরাপদ সঞ্চয়', 'safeSpare.monthly': 'নিরাপদ মাসিক অবদান',
  'leak.usageQuestion': 'গত ৩০ দিনে আপনি কি এই পরিষেবা ব্যবহার করেছেন?',
  'common.loading': 'লোড হচ্ছে', 'common.error': 'কিছু ভুল হয়েছে', 'common.retry': 'আবার চেষ্টা করুন',
  'disclaimer.noInvest': 'SafeSpare কখনও আপনার অর্থ বিনিয়োগ বা স্থানান্তর করে না।',
};

const ta: Dict = {
  'app.tagline': 'வாழ்க்கை பாதுகாப்பாக விடக்கூடியதை மட்டுமே முதலீடு செய்யுங்கள்.',
  'nav.dashboard': 'டாஷ்போர்டு', 'nav.spending': 'செலவு', 'nav.safeSpare': 'பாதுகாப்பான சேமிப்பு',
  'nav.roundUps': 'ரவுண்ட்-அப்', 'nav.leakRadar': 'லீக் ரேடார்', 'nav.goals': 'இலக்குகள்',
  'nav.coach': 'உதவியாளர்', 'nav.privacy': 'தனியுரிமை',
  'cta.analyze': 'என் செலவைப் பாருங்கள்', 'cta.demo': 'மாதிரி அறிக்கை',
  'cta.listen': 'கேளுங்கள்', 'cta.speak': 'உங்கள் செலவைச் சொல்லுங்கள்', 'cta.stop': 'நிறுத்து',
  'voice.title': 'நீங்கள் என்ன செலவு செய்தீர்கள் என்று சொல்லுங்கள்',
  'voice.prompt': 'மைக்கை அழுத்தி தொகையையும் காரணத்தையும் சொல்லுங்கள்.',
  'voice.listening': 'கேட்கிறோம்…', 'voice.added': 'சேர்க்கப்பட்டது',
  'voice.example': 'உதாரணம்: “நான் காய்கறிக்கு 250 ரூபாய் செலவழித்தேன்”',
  'safeSpare.now': 'இப்போது பாதுகாப்பான சேமிப்பு',
  'leak.usageQuestion': 'கடந்த 30 நாட்களில் இந்தச் சேவையைப் பயன்படுத்தினீர்களா?',
  'common.loading': 'ஏற்றுகிறது', 'common.error': 'ஏதோ தவறு', 'common.retry': 'மீண்டும் முயற்சி',
  'disclaimer.noInvest': 'SafeSpare உங்கள் பணத்தை முதலீடு செய்யவோ நகர்த்தவோ இல்லை.',
};

const te: Dict = {
  'app.tagline': 'జీవితం సురక్షితంగా విడిచిపెట్టగలిగినంతే పెట్టుబడి పెట్టండి.',
  'nav.dashboard': 'డాష్‌బోర్డ్', 'nav.spending': 'ఖర్చు', 'nav.safeSpare': 'సురక్షిత పొదుపు',
  'nav.goals': 'లక్ష్యాలు', 'nav.coach': 'సహాయకుడు', 'nav.privacy': 'గోప్యత',
  'cta.analyze': 'నా ఖర్చు చూడండి', 'cta.speak': 'మీ ఖర్చు చెప్పండి', 'cta.listen': 'వినండి',
  'voice.title': 'మీరు ఏమి ఖర్చు చేశారో చెప్పండి', 'voice.listening': 'వింటున్నాము…',
  'voice.example': 'ఉదాహరణ: “నేను కూరగాయలకు 250 రూపాయలు ఖర్చు చేశాను”',
  'safeSpare.now': 'ఇప్పుడు సురక్షిత పొదుపు',
  'leak.usageQuestion': 'గత 30 రోజుల్లో ఈ సేవను ఉపయోగించారా?',
  'common.loading': 'లోడ్ అవుతోంది', 'common.error': 'ఏదో తప్పు జరిగింది',
  'disclaimer.noInvest': 'SafeSpare మీ డబ్బును పెట్టుబడి పెట్టదు లేదా బదిలీ చేయదు.',
};

const mr: Dict = {
  'app.tagline': 'आयुष्य सुरक्षितपणे देऊ शकेल तेवढीच गुंतवणूक करा.',
  'nav.dashboard': 'डॅशबोर्ड', 'nav.spending': 'खर्च', 'nav.safeSpare': 'सुरक्षित बचत',
  'nav.goals': 'ध्येये', 'nav.coach': 'सहाय्यक', 'nav.privacy': 'गोपनीयता',
  'cta.analyze': 'माझा खर्च पहा', 'cta.speak': 'तुमचा खर्च सांगा', 'cta.listen': 'ऐका',
  'voice.title': 'तुम्ही काय खर्च केले ते सांगा', 'voice.listening': 'ऐकत आहोत…',
  'voice.example': 'उदा: “मी भाजीवर 250 रुपये खर्च केले”',
  'leak.usageQuestion': 'गेल्या 30 दिवसांत तुम्ही ही सेवा वापरली का?',
  'common.loading': 'लोड होत आहे', 'common.error': 'काहीतरी चूक झाली',
  'disclaimer.noInvest': 'SafeSpare तुमचे पैसे कधीही गुंतवत नाही.',
};

const gu: Dict = {
  'app.tagline': 'જીવન સુરક્ષિત રીતે છોડી શકે તેટલું જ રોકાણ કરો.',
  'nav.dashboard': 'ડેશબોર્ડ', 'nav.spending': 'ખર્ચ', 'nav.safeSpare': 'સુરક્ષિત બચત',
  'nav.goals': 'લક્ષ્યો', 'nav.privacy': 'ગોપનીયતા',
  'cta.analyze': 'મારો ખર્ચ જુઓ', 'cta.speak': 'તમારો ખર્ચ બોલો', 'cta.listen': 'સાંભળો',
  'voice.title': 'તમે શું ખર્ચ કર્યો તે કહો', 'voice.listening': 'સાંભળી રહ્યા છીએ…',
  'voice.example': 'દા.ત.: “મેં શાકભાજી પર 250 રૂપિયા ખર્ચ્યા”',
  'common.loading': 'લોડ થઈ રહ્યું છે', 'common.error': 'કંઈક ખોટું થયું',
  'disclaimer.noInvest': 'SafeSpare તમારા પૈસા ક્યારેય રોકાણ કરતું નથી.',
};

const kn: Dict = {
  'app.tagline': 'ಜೀವನ ಸುರಕ್ಷಿತವಾಗಿ ಬಿಡಬಹುದಾದಷ್ಟನ್ನೇ ಹೂಡಿಕೆ ಮಾಡಿ.',
  'nav.dashboard': 'ಡ್ಯಾಶ್‌ಬೋರ್ಡ್', 'nav.spending': 'ಖರ್ಚು', 'nav.safeSpare': 'ಸುರಕ್ಷಿತ ಉಳಿತಾಯ',
  'nav.goals': 'ಗುರಿಗಳು', 'nav.privacy': 'ಗೌಪ್ಯತೆ',
  'cta.analyze': 'ನನ್ನ ಖರ್ಚು ನೋಡಿ', 'cta.speak': 'ನಿಮ್ಮ ಖರ್ಚು ಹೇಳಿ', 'cta.listen': 'ಕೇಳಿ',
  'voice.title': 'ನೀವು ಏನು ಖರ್ಚು ಮಾಡಿದಿರಿ ಎಂದು ಹೇಳಿ', 'voice.listening': 'ಕೇಳುತ್ತಿದ್ದೇವೆ…',
  'voice.example': 'ಉದಾ: “ನಾನು ತರಕಾರಿಗೆ 250 ರೂಪಾಯಿ ಖರ್ಚು ಮಾಡಿದೆ”',
  'common.loading': 'ಲೋಡ್ ಆಗುತ್ತಿದೆ', 'common.error': 'ಏನೋ ತಪ್ಪಾಗಿದೆ',
  'disclaimer.noInvest': 'SafeSpare ನಿಮ್ಮ ಹಣವನ್ನು ಎಂದಿಗೂ ಹೂಡಿಕೆ ಮಾಡುವುದಿಲ್ಲ.',
};

const ml: Dict = {
  'app.tagline': 'ജീവിതം സുരക്ഷിതമായി വിട്ടുനൽകാവുന്നത് മാത്രം നിക്ഷേപിക്കുക.',
  'nav.dashboard': 'ഡാഷ്‌ബോർഡ്', 'nav.spending': 'ചെലവ്', 'nav.safeSpare': 'സുരക്ഷിത സമ്പാദ്യം',
  'nav.goals': 'ലക്ഷ്യങ്ങൾ', 'nav.privacy': 'സ്വകാര്യത',
  'cta.analyze': 'എന്റെ ചെലവ് കാണുക', 'cta.speak': 'നിങ്ങളുടെ ചെലവ് പറയുക', 'cta.listen': 'കേൾക്കുക',
  'voice.title': 'നിങ്ങൾ എന്ത് ചെലവാക്കി എന്ന് പറയുക', 'voice.listening': 'കേൾക്കുന്നു…',
  'voice.example': 'ഉദാ: “ഞാൻ പച്ചക്കറിക്ക് 250 രൂപ ചെലവാക്കി”',
  'common.loading': 'ലോഡ് ചെയ്യുന്നു', 'common.error': 'എന്തോ തെറ്റ് സംഭവിച്ചു',
  'disclaimer.noInvest': 'SafeSpare നിങ്ങളുടെ പണം ഒരിക്കലും നിക്ഷേപിക്കുന്നില്ല.',
};

const pa: Dict = {
  'app.tagline': 'ਜ਼ਿੰਦਗੀ ਸੁਰੱਖਿਅਤ ਢੰਗ ਨਾਲ ਜਿੰਨਾ ਛੱਡ ਸਕੇ, ਓਨਾ ਹੀ ਨਿਵੇਸ਼ ਕਰੋ।',
  'nav.dashboard': 'ਡੈਸ਼ਬੋਰਡ', 'nav.spending': 'ਖਰਚ', 'nav.safeSpare': 'ਸੁਰੱਖਿਅਤ ਬੱਚਤ',
  'nav.goals': 'ਟੀਚੇ', 'nav.privacy': 'ਗੋਪਨੀਯਤਾ',
  'cta.analyze': 'ਮੇਰਾ ਖਰਚ ਵੇਖੋ', 'cta.speak': 'ਆਪਣਾ ਖਰਚ ਬੋਲੋ', 'cta.listen': 'ਸੁਣੋ',
  'voice.title': 'ਦੱਸੋ ਤੁਸੀਂ ਕੀ ਖਰਚ ਕੀਤਾ', 'voice.listening': 'ਸੁਣ ਰਹੇ ਹਾਂ…',
  'voice.example': 'ਜਿਵੇਂ: “ਮੈਂ ਸਬਜ਼ੀ ਉੱਤੇ 250 ਰੁਪਏ ਖਰਚੇ”',
  'common.loading': 'ਲੋਡ ਹੋ ਰਿਹਾ ਹੈ', 'common.error': 'ਕੁਝ ਗਲਤ ਹੋਇਆ',
  'disclaimer.noInvest': 'SafeSpare ਤੁਹਾਡਾ ਪੈਸਾ ਕਦੇ ਨਿਵੇਸ਼ ਨਹੀਂ ਕਰਦਾ।',
};

const ur: Dict = {
  'app.tagline': 'صرف اتنی رقم لگائیں جتنی زندگی محفوظ طریقے سے بچا سکے۔',
  'nav.dashboard': 'ڈیش بورڈ', 'nav.spending': 'اخراجات', 'nav.safeSpare': 'محفوظ بچت',
  'nav.goals': 'اہداف', 'nav.privacy': 'رازداری',
  'cta.analyze': 'میرے اخراجات دیکھیں', 'cta.speak': 'اپنا خرچ بولیں', 'cta.listen': 'سنیں',
  'voice.title': 'بتائیں آپ نے کیا خرچ کیا', 'voice.listening': 'سن رہے ہیں…',
  'voice.example': 'مثلاً: “میں نے سبزی پر 250 روپے خرچ کیے”',
  'common.loading': 'لوڈ ہو رہا ہے', 'common.error': 'کچھ غلط ہوا',
  'disclaimer.noInvest': 'SafeSpare آپ کا پیسہ کبھی سرمایہ کاری نہیں کرتا۔',
};

const or_: Dict = {
  'app.tagline': 'ଜୀବନ ସୁରକ୍ଷିତ ଭାବେ ଛାଡ଼ିପାରୁଥିବା ପରିମାଣ ହିଁ ବିନିଯୋଗ କରନ୍ତୁ।',
  'nav.dashboard': 'ଡ୍ୟାସବୋର୍ଡ', 'nav.spending': 'ଖର୍ଚ୍ଚ', 'nav.safeSpare': 'ସୁରକ୍ଷିତ ସଞ୍ଚୟ',
  'cta.analyze': 'ମୋ ଖର୍ଚ୍ଚ ଦେଖନ୍ତୁ', 'cta.speak': 'ଆପଣଙ୍କ ଖର୍ଚ୍ଚ କୁହନ୍ତୁ',
  'voice.listening': 'ଶୁଣୁଛୁ…', 'common.loading': 'ଲୋଡ୍ ହେଉଛି',
  'disclaimer.noInvest': 'SafeSpare କେବେ ଆପଣଙ୍କ ଟଙ୍କା ବିନିଯୋଗ କରେ ନାହିଁ।',
};

const as_: Dict = {
  'app.tagline': 'জীৱনে সুৰক্ষিতভাৱে দিব পৰাখিনিহে বিনিয়োগ কৰক।',
  'nav.dashboard': 'ডেশ্ববৰ্ড', 'nav.spending': 'খৰচ', 'nav.safeSpare': 'সুৰক্ষিত সঞ্চয়',
  'cta.analyze': 'মোৰ খৰচ চাওক', 'cta.speak': 'আপোনাৰ খৰচ কওক',
  'voice.listening': 'শুনি আছোঁ…', 'common.loading': 'ল\'ড হৈ আছে',
  'disclaimer.noInvest': 'SafeSpare-এ কেতিয়াও আপোনাৰ ধন বিনিয়োগ নকৰে।',
};

const ne: Dict = {
  'app.tagline': 'जीवनले सुरक्षित रूपमा दिन सक्ने जति मात्र लगानी गर्नुहोस्।',
  'nav.dashboard': 'ड्यासबोर्ड', 'nav.spending': 'खर्च', 'nav.safeSpare': 'सुरक्षित बचत',
  'cta.analyze': 'मेरो खर्च हेर्नुहोस्', 'cta.speak': 'आफ्नो खर्च बोल्नुहोस्',
  'voice.listening': 'सुन्दैछौं…', 'common.loading': 'लोड हुँदैछ',
  'disclaimer.noInvest': 'SafeSpare ले तपाईंको पैसा कहिल्यै लगानी गर्दैन।',
};

export const TRANSLATIONS: Record<string, Dict> = {
  en, hi, bn, ta, te, mr, gu, kn, ml, pa, ur,
  or: or_, as: as_, ne,
};

export const EN = en;

/** Share of UI strings translated, for an honest badge in the switcher. */
export function translationCoverage(code: string): number {
  if (code === 'en') return 1;
  const dict = TRANSLATIONS[code];
  if (!dict) return 0;
  const total = Object.keys(en).length;
  return Math.round((Object.keys(dict).length / total) * 100) / 100;
}

export function translate(code: string, key: StringKey): string {
  return TRANSLATIONS[code]?.[key] ?? en[key];
}
