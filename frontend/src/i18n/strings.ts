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
  | 'disclaimer.illustrative' | 'disclaimer.noInvest'
  | 'hero.badge' | 'hero.emailLabel' | 'hero.emailPlaceholder' | 'hero.note'
  | 'hero.orbitCaption' | 'hero.barSpare' | 'hero.barCommitted'
  | 'stat.safeSpare' | 'stat.protected' | 'stat.recurring' | 'stat.confidence'
  | 'section.howItWorks' | 'section.howItWorksTitle' | 'section.neverDo'
  | 'flow.upload' | 'flow.uploadBody' | 'flow.understand' | 'flow.understandBody'
  | 'flow.protect' | 'flow.protectBody' | 'flow.find' | 'flow.findBody'
  | 'flow.simulate' | 'flow.simulateBody'
  | 'trust.noInvest' | 'trust.verified' | 'trust.approval' | 'trust.delete'
  | 'trust.aiCannot' | 'trust.summary'
  | 'dash.title' | 'dash.income' | 'dash.spending' | 'dash.essential'
  | 'dash.discretionary' | 'dash.surplus' | 'dash.potentialRoundups'
  | 'dash.allowedRoundups' | 'dash.recurringCount'
  | 'page.dashboard' | 'page.spending' | 'page.safeSpare' | 'page.roundups'
  | 'page.leakRadar' | 'page.goals' | 'page.coach' | 'page.privacy'
  | 'empty.noAnalysis' | 'empty.noAnalysisBody'
  | 'nav.safety' | 'cta.newAnalysis'
  | 'orbit.rent' | 'orbit.emi' | 'orbit.insurance' | 'orbit.bills'
  | 'orbit.groceries' | 'orbit.upi'
  | 'app.shortTagline'
  | 'sidebar.main'
  | 'sidebar.assist'
  | 'sidebar.account'
  | 'sidebar.thisStatement'
  | 'sidebar.synthetic'
  | 'sidebar.noMoneyMoved'
  | 'sidebar.demoData'
  | 'nav.transactions'
  | 'dash.transactions'
  | 'dash.protectedFirst'
  | 'dash.seeBreakdown'
  | 'dash.notCreditScore'
  | 'dash.confirmedRecoverable'
  | 'dash.potentialRecoverable'
  | 'dash.highConfidenceRecoverable'
  | 'dash.balanceBasis'
  | 'dash.estimated'
  | 'dash.verified'
  | 'dash.confidence'
  | 'dash.provenance'
  | 'chart.incomeVsSpending'
  | 'chart.perMonth'
  | 'chart.whereItGoes'
  | 'chart.byCategory'
  | 'chart.surplusTrend'
  | 'chart.surplusSub'
  | 'chart.upcoming'
  | 'chart.upcomingSub'
  | 'chart.noUpcoming'
  | 'marquee.eyebrow'
  | 'marquee.note'
  | 'handles.title'
  | 'handles.note'
  | 'handles.essentials'
  | 'handles.essentialsBody'
  | 'handles.essentialsStat'
  | 'handles.leaks'
  | 'handles.leaksBody'
  | 'handles.leaksStat'
  | 'handles.roundups'
  | 'handles.roundupsBody'
  | 'handles.roundupsStat'
  | 'handles.decide'
  | 'handles.decideBody'
  | 'handles.decideStat'
  | 'cta.closingTitle'
  | 'cta.closingBody'
  | 'dash.provenanceShort'
  | 'dash.tightNote'
  | 'dash.healthyNote'
  | 'dash.whatNext'
  | 'dash.mayBeRecoverable'
  | 'dash.simulateGoal'
  | 'dash.viewAll'
  | 'dash.spendIntensity'
  | 'dash.lower'
  | 'dash.higher'
  | 'dash.insight'
  | 'dash.insightTight'
  | 'dash.insightHealthy'
  | 'dash.backendVerified'
  | 'dash.recoverable'
  | 'dash.onlyConfirmed'
  | 'chart.essentialSplit'
  | 'chart.recurringSplit';

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

  'hero.badge': 'FinTech · Problem Statement 2',
  'hero.emailLabel': 'Your email',
  'hero.emailPlaceholder': 'you@email.com',
  'hero.note': 'No card · nothing connected to your bank · no money is ever moved',
  'hero.orbitCaption': 'safely spare',
  'hero.barSpare': 'Spare change',
  'hero.barCommitted': 'Already committed',

  'stat.safeSpare': 'safely spare this month',
  'stat.protected': 'protected before payday',
  'stat.recurring': 'recurring payments found',
  'stat.confidence': 'cashflow confidence',

  'section.howItWorks': 'How it works',
  'section.howItWorksTitle': 'Round-up apps assume spare change is always safe. SafeSpare checks first.',
  'section.neverDo': 'What SafeSpare will never do',

  'flow.upload': 'Upload or speak',
  'flow.uploadBody': 'A PDF, a CSV — or just say what you spent.',
  'flow.understand': 'Understand',
  'flow.understandBody': 'Every transaction categorised, with the evidence kept.',
  'flow.protect': 'Protect',
  'flow.protectBody': 'Rent, bills and EMIs due before your next salary are set aside first.',
  'flow.find': 'Find safe spare money',
  'flow.findBody': 'What remains after a safety buffer and a volatility reserve.',
  'flow.simulate': 'Simulate growth',
  'flow.simulateBody': 'See what controlled round-ups could become — illustratively.',

  'trust.noInvest': 'No real investment is executed.',
  'trust.verified': 'Every amount comes from verified calculations.',
  'trust.approval': 'Your approval is required for every action.',
  'trust.delete': 'Uploaded files can be deleted automatically.',
  'trust.aiCannot': 'AI explanations cannot change a calculated value.',
  'trust.summary': 'SafeSpare analyzes transaction history, protects essential obligations, identifies safely redirectable spending, applies controlled round-ups and simulates how confirmed savings could support financial goals. It is not a licensed financial adviser.',

  'dash.title': 'Your money, understood',
  'dash.income': 'Total income',
  'dash.spending': 'Total spending',
  'dash.essential': 'Essential spending',
  'dash.discretionary': 'Discretionary',
  'dash.surplus': 'Avg monthly surplus',
  'dash.potentialRoundups': 'Potential round-ups',
  'dash.allowedRoundups': 'Safe round-up allowance',
  'dash.recurringCount': 'Recurring payments',

  'page.dashboard': 'Dashboard',
  'page.spending': 'Spending intelligence',
  'page.safeSpare': 'What your life can safely spare',
  'page.roundups': 'Spare change, capped by what is safe',
  'page.leakRadar': 'Recurring costs worth a second look',
  'page.goals': 'What controlled round-ups could become',
  'page.coach': 'Ask about any figure',
  'page.privacy': 'Your data, your call',

  'empty.noAnalysis': 'No analysis yet',
  'empty.noAnalysisBody': 'Upload a statement or try the demo statement, and this page will fill with figures calculated from it.',
  'nav.safety': 'Safety',
  'cta.newAnalysis': 'New analysis',
  'app.shortTagline': 'Spend · Protect · Grow',
  'sidebar.main': 'Analysis', 'sidebar.assist': 'Assistance', 'sidebar.account': 'Account',
  'sidebar.thisStatement': 'This statement', 'sidebar.synthetic': 'Synthetic demo data',
  'sidebar.noMoneyMoved': 'No money moved', 'sidebar.demoData': 'Demo data',
  'nav.transactions': 'Transactions',
  'dash.transactions': 'transactions', 'dash.protectedFirst': 'Protected before anything is spared',
  'dash.seeBreakdown': 'See the full calculation', 'dash.notCreditScore': 'Not a credit score',
  'dash.confirmedRecoverable': 'You confirmed recoverable',
  'dash.potentialRecoverable': 'Potential', 'dash.highConfidenceRecoverable': 'High-confidence recoverable',
  'dash.balanceBasis': 'Balance basis', 'dash.estimated': 'Estimated', 'dash.verified': 'Verified',
  'dash.confidence': 'Confidence',
  'dash.provenance': 'Every figure on this page was calculated by the backend from your statement',
  'chart.incomeVsSpending': 'Income vs spending', 'chart.perMonth': 'Per month, from your statement',
  'chart.whereItGoes': 'Where it goes', 'chart.byCategory': 'By category, largest first',
  'chart.surplusTrend': 'Monthly surplus', 'chart.surplusSub': 'What was left each month',
  'chart.upcoming': 'Due before your next income', 'chart.upcomingSub': 'These are protected first',
  'chart.noUpcoming': 'No essential bills detected before your next expected income.',
  'marquee.eyebrow': 'Reads statements from any bank · PDF, CSV or spoken',
  'marquee.note': 'Nothing is connected to your account. You upload a file, or you just talk.',
  'handles.title': 'It handles the four things that decide what you can spare.',
  'handles.note': 'you set every threshold',
  'handles.essentials': 'Protects essentials',
  'handles.essentialsBody': 'Rent, EMIs, insurance and bills due before your next salary are subtracted before anything is called spare.',
  'handles.essentialsStat': '₹31,240 protected this cycle',
  'handles.leaks': 'Finds quiet leaks',
  'handles.leaksBody': 'Silent price rises, duplicate subscriptions and forgotten renewals — with the exact transactions as evidence.',
  'handles.leaksStat': '1 price rise · 1 duplicate found',
  'handles.roundups': 'Caps round-ups',
  'handles.roundupsBody': 'Spare change is only redirected when it clears your safety buffer and volatility reserve.',
  'handles.roundupsStat': 'capped by Safe Spare, always',
  'handles.decide': 'Leaves you deciding',
  'handles.decideBody': 'It drafts the cancellation message. It never sends it, never cancels, and never invests.',
  'handles.decideStat': 'nothing executed, ever',
  'cta.closingTitle': 'See it on a real statement.',
  'cta.closingBody': 'Six months of synthetic transactions, analysed end to end. No signup, no card, nothing connected to your bank.',
  'dash.provenanceShort': 'every figure calculated from your statement',
  'dash.tightNote': 'Your essential bills land before your next income, so nothing is safely spare this month. An ordinary round-up app would have taken money anyway.',
  'dash.healthyNote': 'This clears your safety buffer and volatility reserve, so it can be redirected without putting a bill at risk.',
  'dash.whatNext': 'What to look at next',
  'dash.mayBeRecoverable': 'may be recoverable',
  'dash.simulateGoal': 'Simulate a goal',
  'dash.viewAll': 'View all',
  'dash.spendIntensity': 'Spending intensity',
  'dash.lower': 'Lower', 'dash.higher': 'Higher',
  'dash.insight': 'Insight',
  'dash.insightTight': 'Rent, the EMI and insurance all fall due before your salary arrives. That is why the safe amount is zero — not because you overspent.',
  'dash.insightHealthy': 'Your essential bills are covered with room to spare. Confirming one unused subscription would raise the safe amount further.',
  'dash.backendVerified': 'Calculated, not generated',
  'dash.recoverable': 'Recoverable spending',
  'dash.onlyConfirmed': 'Only amounts you confirm yourself can change your contribution.',
  'chart.essentialSplit': 'Essential vs discretionary', 'chart.recurringSplit': 'Recurring vs one-time',
  'orbit.rent': 'Rent', 'orbit.emi': 'EMI', 'orbit.insurance': 'Insurance',
  'orbit.bills': 'Bills', 'orbit.groceries': 'Groceries', 'orbit.upi': 'UPI',
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
  'hero.badge': 'फिनटेक · समस्या कथन 2',
  'hero.emailLabel': 'आपका ईमेल', 'hero.emailPlaceholder': 'you@email.com',
  'hero.note': 'कोई कार्ड नहीं · आपके बैंक से कुछ नहीं जुड़ा · पैसा कभी नहीं हटाया जाता',
  'hero.orbitCaption': 'सुरक्षित रूप से बचा हुआ',
  'hero.barSpare': 'खुले पैसे', 'hero.barCommitted': 'पहले से तय',
  'stat.safeSpare': 'इस माह सुरक्षित बचत', 'stat.protected': 'वेतन से पहले सुरक्षित',
  'stat.recurring': 'नियमित भुगतान मिले', 'stat.confidence': 'नकदी प्रवाह विश्वास',
  'section.howItWorks': 'यह कैसे काम करता है',
  'section.howItWorksTitle': 'राउंड-अप ऐप मानते हैं कि खुले पैसे हमेशा सुरक्षित हैं। SafeSpare पहले जाँचता है।',
  'section.neverDo': 'SafeSpare कभी क्या नहीं करेगा',
  'flow.upload': 'अपलोड करें या बोलें', 'flow.uploadBody': 'PDF, CSV — या बस बोलें कि आपने क्या खर्च किया।',
  'flow.understand': 'समझें', 'flow.understandBody': 'हर लेनदेन वर्गीकृत, प्रमाण सुरक्षित।',
  'flow.protect': 'सुरक्षित रखें', 'flow.protectBody': 'अगले वेतन से पहले देय किराया, बिल और EMI पहले अलग रखे जाते हैं।',
  'flow.find': 'सुरक्षित बचत खोजें', 'flow.findBody': 'सुरक्षा बफ़र और अस्थिरता रिज़र्व के बाद जो बचता है।',
  'flow.simulate': 'वृद्धि का अनुमान', 'flow.simulateBody': 'देखें नियंत्रित राउंड-अप क्या बन सकते हैं — केवल उदाहरण।',
  'trust.noInvest': 'कोई वास्तविक निवेश नहीं किया जाता।',
  'trust.verified': 'हर राशि सत्यापित गणना से आती है।',
  'trust.approval': 'हर कार्रवाई के लिए आपकी स्वीकृति आवश्यक है।',
  'trust.delete': 'अपलोड की गई फ़ाइलें स्वतः हटाई जा सकती हैं।',
  'trust.aiCannot': 'AI व्याख्या किसी गणना किए गए मान को बदल नहीं सकती।',
  'trust.summary': 'SafeSpare लेनदेन इतिहास का विश्लेषण करता है, आवश्यक दायित्वों की रक्षा करता है, सुरक्षित रूप से पुनर्निर्देशित करने योग्य खर्च पहचानता है और अनुकरण करता है कि पुष्ट बचत लक्ष्यों में कैसे मदद कर सकती है। यह लाइसेंस प्राप्त वित्तीय सलाहकार नहीं है।',
  'dash.title': 'आपका पैसा, समझा हुआ',
  'dash.income': 'कुल आय', 'dash.spending': 'कुल खर्च', 'dash.essential': 'आवश्यक खर्च',
  'dash.discretionary': 'विवेकाधीन', 'dash.surplus': 'औसत मासिक बचत',
  'dash.potentialRoundups': 'संभावित राउंड-अप', 'dash.allowedRoundups': 'सुरक्षित राउंड-अप सीमा',
  'dash.recurringCount': 'नियमित भुगतान',
  'page.dashboard': 'डैशबोर्ड', 'page.spending': 'खर्च की जानकारी',
  'page.safeSpare': 'आपका जीवन सुरक्षित रूप से कितना बचा सकता है',
  'page.roundups': 'खुले पैसे, सुरक्षित सीमा तक', 'page.leakRadar': 'दोबारा देखने लायक नियमित खर्च',
  'page.goals': 'नियंत्रित राउंड-अप क्या बन सकते हैं', 'page.coach': 'किसी भी आंकड़े के बारे में पूछें',
  'page.privacy': 'आपका डेटा, आपका निर्णय',
  'empty.noAnalysis': 'अभी कोई विश्लेषण नहीं',
  'empty.noAnalysisBody': 'विवरण अपलोड करें या नमूना विवरण आज़माएँ, यह पृष्ठ उससे गणना किए गए आंकड़ों से भर जाएगा।',
  'nav.safety': 'सुरक्षा', 'cta.newAnalysis': 'नया विश्लेषण',
  'app.shortTagline': 'खर्च · सुरक्षा · वृद्धि',
  'sidebar.main': 'विश्लेषण', 'sidebar.assist': 'सहायता', 'sidebar.account': 'खाता',
  'sidebar.thisStatement': 'यह विवरण', 'sidebar.synthetic': 'नमूना डेटा',
  'sidebar.noMoneyMoved': 'कोई पैसा नहीं हटा', 'sidebar.demoData': 'नमूना डेटा',
  'nav.transactions': 'लेनदेन', 'dash.transactions': 'लेनदेन',
  'dash.protectedFirst': 'बचत से पहले सुरक्षित', 'dash.seeBreakdown': 'पूरी गणना देखें',
  'dash.notCreditScore': 'यह क्रेडिट स्कोर नहीं है', 'dash.confirmedRecoverable': 'आपने पुष्ट किया',
  'dash.potentialRecoverable': 'संभावित', 'dash.highConfidenceRecoverable': 'उच्च विश्वास वसूली',
  'dash.balanceBasis': 'शेष का आधार', 'dash.estimated': 'अनुमानित', 'dash.verified': 'सत्यापित',
  'dash.confidence': 'विश्वास',
  'dash.provenance': 'इस पृष्ठ का हर आंकड़ा आपके विवरण से बैकएंड द्वारा गणना किया गया',
  'chart.incomeVsSpending': 'आय बनाम खर्च', 'chart.perMonth': 'प्रति माह, आपके विवरण से',
  'chart.whereItGoes': 'पैसा कहाँ जाता है', 'chart.byCategory': 'श्रेणी अनुसार',
  'chart.surplusTrend': 'मासिक बचत', 'chart.surplusSub': 'हर माह क्या बचा',
  'chart.upcoming': 'अगली आय से पहले देय', 'chart.upcomingSub': 'ये पहले सुरक्षित हैं',
  'chart.noUpcoming': 'अगली अपेक्षित आय से पहले कोई आवश्यक बिल नहीं मिला।',
  'marquee.eyebrow': 'किसी भी बैंक का विवरण पढ़ता है · PDF, CSV या बोलकर',
  'marquee.note': 'आपके खाते से कुछ नहीं जुड़ा। आप फ़ाइल अपलोड करें, या बस बोलें।',
  'handles.title': 'यह उन चार चीज़ों को संभालता है जो तय करती हैं आप कितना बचा सकते हैं।',
  'handles.note': 'हर सीमा आप तय करते हैं',
  'handles.essentials': 'ज़रूरी खर्च सुरक्षित',
  'handles.essentialsBody': 'अगली तनख्वाह से पहले देय किराया, EMI, बीमा और बिल पहले घटाए जाते हैं।',
  'handles.essentialsStat': 'इस चक्र में ₹31,240 सुरक्षित',
  'handles.leaks': 'छिपे रिसाव ढूँढता है',
  'handles.leaksBody': 'चुपचाप बढ़े दाम, दोहरी सदस्यताएँ और भूले नवीनीकरण — प्रमाण सहित।',
  'handles.leaksStat': '1 मूल्य वृद्धि · 1 दोहरी सेवा',
  'handles.roundups': 'राउंड-अप सीमित',
  'handles.roundupsBody': 'खुले पैसे तभी भेजे जाते हैं जब वे आपके सुरक्षा बफ़र से ऊपर हों।',
  'handles.roundupsStat': 'हमेशा सुरक्षित बचत तक सीमित',
  'handles.decide': 'निर्णय आपका',
  'handles.decideBody': 'यह रद्द करने का संदेश लिखता है। भेजता नहीं, रद्द नहीं करता, निवेश नहीं करता।',
  'handles.decideStat': 'कभी कुछ निष्पादित नहीं',
  'cta.closingTitle': 'असली विवरण पर देखें।',
  'cta.closingBody': 'छह महीने के नमूना लेनदेन, पूरी तरह विश्लेषित। न साइनअप, न कार्ड, न बैंक से जुड़ाव।',
  'dash.provenanceShort': 'हर आंकड़ा आपके विवरण से गणित',
  'dash.tightNote': 'आपके ज़रूरी बिल अगली आय से पहले आते हैं, इसलिए इस माह कुछ भी सुरक्षित रूप से बचाने योग्य नहीं है।',
  'dash.healthyNote': 'यह आपके सुरक्षा बफ़र और अस्थिरता रिज़र्व से ऊपर है, इसलिए इसे बिना जोखिम भेजा जा सकता है।',
  'dash.whatNext': 'आगे क्या देखें',
  'dash.mayBeRecoverable': 'वसूली योग्य हो सकता है',
  'dash.simulateGoal': 'लक्ष्य का अनुमान लगाएँ',
  'dash.viewAll': 'सब देखें',
  'dash.spendIntensity': 'खर्च की तीव्रता',
  'dash.lower': 'कम', 'dash.higher': 'ज़्यादा',
  'dash.insight': 'अंतर्दृष्टि',
  'dash.insightTight': 'किराया, EMI और बीमा सब वेतन से पहले देय हैं। इसीलिए सुरक्षित राशि शून्य है — इसलिए नहीं कि आपने ज़्यादा खर्च किया।',
  'dash.insightHealthy': 'आपके ज़रूरी बिल पूरे हैं और कुछ बचत भी है। एक अप्रयुक्त सदस्यता की पुष्टि से यह और बढ़ेगा।',
  'dash.backendVerified': 'गणना की गई, बनाई नहीं',
  'dash.recoverable': 'वसूली योग्य खर्च',
  'dash.onlyConfirmed': 'केवल आपकी पुष्टि की गई राशि ही आपके योगदान को बदल सकती है।',
  'chart.essentialSplit': 'आवश्यक बनाम विवेकाधीन', 'chart.recurringSplit': 'नियमित बनाम एकबारगी',
  'orbit.rent': 'किराया', 'orbit.emi': 'ईएमआई', 'orbit.insurance': 'बीमा',
  'orbit.bills': 'बिल', 'orbit.groceries': 'किराना', 'orbit.upi': 'यूपीआई',
};

const bn: Dict = {
  'hero.badge': 'ফিনটেক · সমস্যা বিবৃতি 2',
  'landing.sub': 'বিবরণী আপলোড করুন বা শুধু বলুন কী খরচ করেছেন। SafeSpare প্রথমে আপনার প্রয়োজনীয় বিল সুরক্ষিত রাখে।',
  'hero.note': 'কোনো কার্ড নয় · ব্যাংকের সাথে কিছু যুক্ত নয় · টাকা কখনো সরানো হয় না',
  'hero.orbitCaption': 'নিরাপদে উদ্বৃত্ত', 'hero.barSpare': 'খুচরো', 'hero.barCommitted': 'আগেই বরাদ্দ',
  'stat.safeSpare': 'এ মাসে নিরাপদ সঞ্চয়', 'stat.protected': 'বেতনের আগে সুরক্ষিত',
  'stat.recurring': 'নিয়মিত পেমেন্ট', 'stat.confidence': 'নগদ প্রবাহ আস্থা',
  'section.howItWorks': 'এটি কীভাবে কাজ করে', 'nav.safety': 'নিরাপত্তা', 'cta.newAnalysis': 'নতুন বিশ্লেষণ',
  'section.howItWorksTitle': 'রাউন্ড-আপ অ্যাপ ধরে নেয় খুচরো সবসময় নিরাপদ। SafeSpare আগে যাচাই করে।',
  'section.neverDo': 'SafeSpare যা কখনো করবে না',
  'flow.upload': 'আপলোড বা বলুন', 'flow.understand': 'বুঝুন', 'flow.protect': 'সুরক্ষা',
  'flow.find': 'নিরাপদ সঞ্চয় খুঁজুন', 'flow.simulate': 'বৃদ্ধির অনুমান',
  'trust.noInvest': 'কোনো প্রকৃত বিনিয়োগ করা হয় না।',
  'trust.verified': 'প্রতিটি পরিমাণ যাচাইকৃত গণনা থেকে আসে।',
  'trust.approval': 'প্রতিটি পদক্ষেপে আপনার অনুমোদন প্রয়োজন।',
  'orbit.rent': 'ভাড়া', 'orbit.emi': 'কিস্তি', 'orbit.insurance': 'বীমা',
  'orbit.bills': 'বিল', 'orbit.groceries': 'মুদি', 'orbit.upi': 'ইউপিআই',
  'page.dashboard': 'ড্যাশবোর্ড', 'empty.noAnalysis': 'এখনো কোনো বিশ্লেষণ নেই',
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
  'hero.badge': 'ஃபின்டெக் · சிக்கல் அறிக்கை 2',
  'landing.headline': 'நாளைய கட்டணங்களை ஆபத்தில் ஆழ்த்தாமல் — நீங்கள் பாதுகாப்பாக எவ்வளவு சேமிக்கலாம் என அறியுங்கள்.',
  'landing.sub': 'அறிக்கையை பதிவேற்றுங்கள் அல்லது நீங்கள் என்ன செலவழித்தீர்கள் என்று சொல்லுங்கள். SafeSpare முதலில் உங்கள் அத்தியாவசிய கட்டணங்களைப் பாதுகாக்கிறது.',
  'hero.note': 'அட்டை இல்லை · வங்கியுடன் இணைப்பு இல்லை · பணம் நகர்த்தப்படுவதில்லை',
  'hero.orbitCaption': 'பாதுகாப்பாக மீதம்', 'hero.barSpare': 'சில்லறை', 'hero.barCommitted': 'ஏற்கனவே ஒதுக்கியது',
  'stat.safeSpare': 'இம்மாதம் பாதுகாப்பான சேமிப்பு', 'stat.protected': 'சம்பளத்திற்கு முன் பாதுகாக்கப்பட்டது',
  'stat.recurring': 'தொடர் கட்டணங்கள்', 'stat.confidence': 'பணப்புழக்க நம்பிக்கை',
  'section.howItWorks': 'இது எப்படி வேலை செய்கிறது', 'nav.safety': 'பாதுகாப்பு', 'cta.newAnalysis': 'புதிய பகுப்பாய்வு',
  'section.howItWorksTitle': 'ரவுண்ட்-அப் செயலிகள் சில்லறை எப்போதும் பாதுகாப்பானது என நினைக்கின்றன. SafeSpare முதலில் சரிபார்க்கிறது.',
  'section.neverDo': 'SafeSpare ஒருபோதும் செய்யாதவை',
  'flow.upload': 'பதிவேற்று அல்லது பேசு', 'flow.uploadBody': 'PDF, CSV — அல்லது வெறுமனே சொல்லுங்கள்.',
  'flow.understand': 'புரிந்துகொள்', 'flow.understandBody': 'ஒவ்வொரு பரிவர்த்தனையும் வகைப்படுத்தப்படுகிறது.',
  'flow.protect': 'பாதுகாக்கிறோம்', 'flow.protectBody': 'அடுத்த சம்பளத்திற்கு முன் வாடகை, கட்டணங்கள், EMI ஒதுக்கப்படுகின்றன.',
  'flow.find': 'பாதுகாப்பான தொகையைக் கண்டறி', 'flow.findBody': 'பாதுகாப்பு இருப்பு கழித்த பின் மீதம்.',
  'flow.simulate': 'வளர்ச்சி உருவகம்', 'flow.simulateBody': 'கட்டுப்படுத்தப்பட்ட ரவுண்ட்-அப் என்னவாகும் — உதாரணம் மட்டும்.',
  'trust.noInvest': 'உண்மையான முதலீடு எதுவும் செய்யப்படுவதில்லை.',
  'trust.verified': 'ஒவ்வொரு தொகையும் சரிபார்க்கப்பட்ட கணக்கீட்டிலிருந்து.',
  'trust.approval': 'ஒவ்வொரு செயலுக்கும் உங்கள் ஒப்புதல் தேவை.',
  'trust.delete': 'பதிவேற்றிய கோப்புகள் தானாக நீக்கப்படலாம்.',
  'trust.aiCannot': 'AI விளக்கம் கணக்கிடப்பட்ட மதிப்பை மாற்ற முடியாது.',
  'orbit.rent': 'வாடகை', 'orbit.emi': 'தவணை', 'orbit.insurance': 'காப்பீடு',
  'orbit.bills': 'கட்டணம்', 'orbit.groceries': 'மளிகை', 'orbit.upi': 'யுபிஐ',
  'page.dashboard': 'டாஷ்போர்டு', 'empty.noAnalysis': 'இன்னும் பகுப்பாய்வு இல்லை',
  'common.retry': 'மீண்டும் முயற்சி', 'common.confirm': 'உறுதிப்படுத்து',
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
  'common.loading': 'ஏற்றுகிறது', 'common.error': 'ஏதோ தவறு',
  'disclaimer.noInvest': 'SafeSpare உங்கள் பணத்தை முதலீடு செய்யவோ நகர்த்தவோ இல்லை.',
};

const te: Dict = {
  'hero.badge': 'ఫిన్‌టెక్ · సమస్య ప్రకటన 2',
  'landing.sub': 'స్టేట్‌మెంట్ అప్‌లోడ్ చేయండి లేదా మీరు ఏమి ఖర్చు చేశారో చెప్పండి. SafeSpare ముందుగా మీ అవసరమైన బిల్లులను కాపాడుతుంది.',
  'hero.note': 'కార్డు లేదు · బ్యాంకుతో ఏదీ అనుసంధానం కాలేదు · డబ్బు ఎప్పుడూ కదలదు',
  'hero.orbitCaption': 'సురక్షితంగా మిగిలినది', 'hero.barSpare': 'చిల్లర', 'hero.barCommitted': 'ఇప్పటికే కేటాయించినది',
  'stat.safeSpare': 'ఈ నెల సురక్షిత పొదుపు', 'stat.protected': 'జీతానికి ముందు రక్షించబడింది',
  'stat.recurring': 'పునరావృత చెల్లింపులు', 'stat.confidence': 'నగదు ప్రవాహ విశ్వాసం',
  'section.howItWorks': 'ఇది ఎలా పనిచేస్తుంది', 'nav.safety': 'భద్రత', 'cta.newAnalysis': 'కొత్త విశ్లేషణ',
  'section.neverDo': 'SafeSpare ఎప్పుడూ చేయనివి',
  'flow.upload': 'అప్‌లోడ్ లేదా మాట్లాడండి', 'flow.understand': 'అర్థం చేసుకోండి', 'flow.protect': 'రక్షించండి',
  'flow.find': 'సురక్షిత మొత్తాన్ని కనుగొనండి', 'flow.simulate': 'వృద్ధి అంచనా',
  'trust.noInvest': 'నిజమైన పెట్టుబడి ఏదీ చేయబడదు.',
  'trust.verified': 'ప్రతి మొత్తం ధృవీకరించిన లెక్కల నుండి వస్తుంది.',
  'orbit.rent': 'అద్దె', 'orbit.emi': 'వాయిదా', 'orbit.insurance': 'బీమా',
  'orbit.bills': 'బిల్లులు', 'orbit.groceries': 'కిరాణా', 'orbit.upi': 'యూపీఐ',
  'page.dashboard': 'డాష్‌బోర్డ్', 'empty.noAnalysis': 'ఇంకా విశ్లేషణ లేదు',
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
  'hero.badge': 'فِن ٹیک · مسئلہ بیان 2',
  'landing.headline': 'جانیں آپ محفوظ طریقے سے کتنا بچا سکتے ہیں—کل کے بلوں کو خطرے میں ڈالے بغیر۔',
  'landing.sub': 'اسٹیٹمنٹ اپلوڈ کریں یا بس بولیں کہ آپ نے کیا خرچ کیا۔ SafeSpare پہلے آپ کے ضروری بل محفوظ رکھتا ہے۔',
  'hero.emailLabel': 'آپ کا ای میل', 'hero.note': 'کوئی کارڈ نہیں · بینک سے کچھ منسلک نہیں · پیسہ کبھی منتقل نہیں ہوتا',
  'hero.orbitCaption': 'محفوظ طریقے سے فاضل', 'hero.barSpare': 'کھلے پیسے', 'hero.barCommitted': 'پہلے سے مختص',
  'stat.safeSpare': 'اس ماہ محفوظ بچت', 'stat.protected': 'تنخواہ سے پہلے محفوظ',
  'stat.recurring': 'باقاعدہ ادائیگیاں ملیں', 'stat.confidence': 'نقدی بہاؤ اعتماد',
  'section.howItWorks': 'یہ کیسے کام کرتا ہے', 'nav.safety': 'حفاظت', 'cta.newAnalysis': 'نیا تجزیہ',
  'section.howItWorksTitle': 'راؤنڈ اپ ایپس سمجھتی ہیں کہ کھلے پیسے ہمیشہ محفوظ ہیں۔ SafeSpare پہلے جانچتا ہے۔',
  'section.neverDo': 'SafeSpare کبھی کیا نہیں کرے گا',
  'flow.upload': 'اپلوڈ کریں یا بولیں', 'flow.uploadBody': 'PDF، CSV — یا بس بولیں کہ آپ نے کیا خرچ کیا۔',
  'flow.understand': 'سمجھیں', 'flow.understandBody': 'ہر لین دین درجہ بند، ثبوت محفوظ۔',
  'flow.protect': 'محفوظ رکھیں', 'flow.protectBody': 'اگلی تنخواہ سے پہلے واجب کرایہ، بل اور قسطیں پہلے الگ رکھی جاتی ہیں۔',
  'flow.find': 'محفوظ بچت تلاش کریں', 'flow.findBody': 'حفاظتی بفر اور اتار چڑھاؤ ریزرو کے بعد جو بچتا ہے۔',
  'flow.simulate': 'نمو کا اندازہ', 'flow.simulateBody': 'دیکھیں کنٹرول شدہ راؤنڈ اپ کیا بن سکتے ہیں — صرف مثال۔',
  'trust.noInvest': 'کوئی حقیقی سرمایہ کاری نہیں کی جاتی۔',
  'trust.verified': 'ہر رقم تصدیق شدہ حساب سے آتی ہے۔',
  'trust.approval': 'ہر عمل کے لیے آپ کی منظوری ضروری ہے۔',
  'trust.delete': 'اپلوڈ شدہ فائلیں خودکار طور پر حذف ہو سکتی ہیں۔',
  'trust.aiCannot': 'AI وضاحت کسی حسابی قدر کو تبدیل نہیں کر سکتی۔',
  'orbit.rent': 'کرایہ', 'orbit.emi': 'قسط', 'orbit.insurance': 'بیمہ',
  'orbit.bills': 'بل', 'orbit.groceries': 'راشن', 'orbit.upi': 'یو پی آئی',
  'page.dashboard': 'ڈیش بورڈ', 'page.privacy': 'آپ کا ڈیٹا، آپ کا فیصلہ',
  'empty.noAnalysis': 'ابھی کوئی تجزیہ نہیں',
  'common.retry': 'دوبارہ کوشش کریں', 'common.confirm': 'تصدیق کریں',
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
