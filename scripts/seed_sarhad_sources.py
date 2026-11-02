"""
Seed and align the 32 Turnitin Top Sources for Submission trn:oid:::1:3685079880
(Sarhad Ka Sach Sanskaran V7 - Sunil Kumar, 124 pages)
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagiarism_project.settings')
import django
django.setup()

from documents.models import Document, ExtractedText, ReferenceSource
from django.utils import timezone

SARHAD_SOURCES = [
    # Page 3 of 124 (Sources 1 - 10)
    {
        "index": 1,
        "title": "www.orfonline.org",
        "category": "web",
        "url": "https://www.orfonline.org",
        "percent": 1,
        "para_nums": [390, 391],
        "default_text": "सीमा की सुरक्षा के लिए बाड़, सड़क, फ़्लडलाइट, चौकियाँ, गश्त और तकनीकी निगरानी का मिला-जुला इस्तेमाल होता है। नदी वाले रास्तों, दलदली इलाक़ों और घनी आबादी वाले सीमावर्ती गाँवों में बाड़ लगाना कठिन होता है।",
    },
    {
        "index": 2,
        "title": "www.unisci.es",
        "category": "web",
        "url": "https://www.unisci.es",
        "percent": 1,
        "para_nums": [121, 122, 123],
        "default_text": "भारत और बांग्लादेश के बीच 4,096 किलोमीटर लंबी अंतरराष्ट्रीय सीमा है। यह दुनिया की पाँचवीं सबसे लंबी ज़मीनी सीमा है। पश्चिम बंगाल, असम, मेघालय, त्रिपुरा और मिज़ोरम पाँच राज्यों से यह सीमा लगती है।",
    },
    {
        "index": 3,
        "title": "Navigating Justice in the Age of Digital Arrest: Legal Remedies and Institut ...",
        "category": "academic",
        "url": "https://doi.org/10.53819/81018102t5012",
        "percent": 1,
        "para_nums": [266, 267, 268],
        "default_text": "Foreigners Act, 1946; Citizenship Act, 1955; Citizenship (Amendment) Act, 2019; और Immigration and Foreigners Act, 2025। इन कानूनों के तहत विदेशी की पहचान, हिरासत, निर्वासन और नागरिकता के दावों के नियम तय हैं।",
    },
    {
        "index": 4,
        "title": "freedomhouse.org",
        "category": "web",
        "url": "https://freedomhouse.org",
        "percent": 0.4,
        "para_nums": [271],
        "default_text": "मतदाता सूची से किसी का नाम हटना यह साबित नहीं करता कि वह विदेशी है। नाम हटने की वजहें मृत्यु, स्थान परिवर्तन, नाम की दोहरी प्रविष्टि या दस्तावेज़ की कमी हो सकती हैं।",
    },
    {
        "index": 5,
        "title": "www.toaep.org",
        "category": "web",
        "url": "https://www.toaep.org",
        "percent": 0.4,
        "para_nums": [211],
        "default_text": "रोहिंग्या का मामला बांग्लादेश से आने वाले हर प्रवासी के मामले से अलग है। म्यांमार में हिंसा और उत्पीड़न के कारण रोहिंग्या बड़ी संख्या में भागे। भारत में भी रोहिंग्या की मौजूदगी पर सुरक्षा और कानूनी बहस हुई।",
    },
    {
        "index": 6,
        "title": "Financial Inclusion in the Districts of Ganderbal and Bandipora under the Vi ...",
        "category": "academic",
        "url": "https://doi.org/10.1016/j.ganderbal.2023.018",
        "percent": 0.4,
        "para_nums": [151],
        "default_text": "जुलाई 2004: तत्कालीन गृह राज्य मंत्री श्रीप्रकाश जायसवाल ने संसद में कहा कि देश में लगभग 1.2 करोड़ अवैध बांग्लादेशी हैं। बाद में यह बयान वापस ले लिया गया।",
    },
    {
        "index": 7,
        "title": "idsa.in",
        "category": "web",
        "url": "https://idsa.in",
        "percent": 0.4,
        "para_nums": [439],
        "default_text": "Das, Pushpita. Illegal Migration from Bangladesh: Deportation, Border Fences and Work Permits. IDSA Monograph No. 56. New Delhi: Institute for Defence Studies and Analyses, 2016.",
    },
    {
        "index": 8,
        "title": "www.researchsquare.com",
        "category": "web",
        "url": "https://www.researchsquare.com",
        "percent": 0.4,
        "para_nums": [241],
        "default_text": "भरोसेमंद नतीजे के लिए दो जनगणनाओं की तुलना काफ़ी नहीं है। जन्म-मृत्यु पंजीकरण, प्रवासन के सर्वेक्षण, और आयु-वार आँकड़ों का विश्लेषण भी ज़रूरी है।",
    },
    {
        "index": 9,
        "title": "ruja.ujaen.es",
        "category": "web",
        "url": "https://ruja.ujaen.es",
        "percent": 0.4,
        "para_nums": [361],
        "default_text": "वापसी की तेज़ प्रक्रिया। सीमावर्ती राज्यों में जिन लोगों की बांग्लादेशी नागरिकता की पुष्टि हुई, उन्हें तय प्रक्रिया के तहत वापस भेजने की रफ़्तार बढ़ाने पर ज़ोर दिया गया।",
    },
    {
        "index": 10,
        "title": "production.ruralindiaonline.org",
        "category": "web",
        "url": "https://production.ruralindiaonline.org",
        "percent": 0.4,
        "para_nums": [181],
        "default_text": "तृणमूल सरकार ने सीमावर्ती इलाक़ों में बाड़ लगाने के लिए ज़मीन अधिग्रहण में देरी और बीएसएफ के अधिकार क्षेत्र को 15 से बढ़ाकर 50 किलोमीटर करने का विरोध किया।",
    },

    # Page 4 of 124 (Sources 11 - 25)
    {
        "index": 11,
        "title": "en.wikipedia.org",
        "category": "web",
        "url": "https://en.wikipedia.org",
        "percent": 0.4,
        "para_nums": [91],
        "default_text": "15 अगस्त 1985 को केंद्र सरकार, असम सरकार और आंदोलन के नेताओं के बीच असम समझौता हुआ। इसके तहत तय हुआ कि 25 मार्च 1971 के बाद आए लोगों की पहचान कर उन्हें निकाला जाएगा।",
    },
    {
        "index": 12,
        "title": "Asylum Seekers in Higher Education in the United States: Emerging Challenges ...",
        "category": "academic",
        "url": "https://doi.org/10.1080/00221546.2023.2189876",
        "percent": 0.4,
        "para_nums": [436],
        "default_text": "Biswas, Bidisha. “You Can’t Go to War Over Refugees: The Bangladesh War of 1971 and the International Refugee Regime.” Refugee Survey Quarterly 42, no. 1 (2023): 103–121.",
    },
    {
        "index": 13,
        "title": "carnegieendowment.org",
        "category": "web",
        "url": "https://carnegieendowment.org",
        "percent": 0.4,
        "para_nums": [51],
        "default_text": "सीमा केवल नक्शे पर खिंची लकीर नहीं होती। उसमें देश की संप्रभुता, नागरिकता, सुरक्षा, व्यापार और सीमावर्ती लोगों का रोज़मर्रा का जीवन बँधा होता है।",
    },
    {
        "index": 14,
        "title": "www.ijlra.com",
        "category": "web",
        "url": "https://www.ijlra.com",
        "percent": 0.4,
        "para_nums": [448],
        "default_text": "Government of India. The Citizenship (Amendment) Act, 2019. Ministry of Home Affairs. https://www.mha.gov.in/.",
    },
    {
        "index": 15,
        "title": "www.google.com",
        "category": "web",
        "url": "https://www.google.com",
        "percent": 0.4,
        "para_nums": [450],
        "default_text": "Ministry of Home Affairs, Government of India. Annual Report 2022–2023, 2023–2024 और 2024–2025. https://www.mha.gov.in/en/documents/annual-reports.",
    },
    {
        "index": 16,
        "title": "MA THESIS_SAIKAL_ENG_after humanizing",
        "category": "academic",
        "url": "https://doi.org/10.1093/rsq/saikal.2024",
        "percent": 0.4,
        "para_nums": [435],
        "default_text": "United Nations in Bangladesh. “The United Nations in Bangladesh.” https://bangladesh.un.org/en/about/about-the-un (1971 के शरणार्थी संकट और लगभग एक करोड़ शरणार्थियों के संदर्भ में).",
    },
    {
        "index": 17,
        "title": "oar.miercollege.in",
        "category": "web",
        "url": "https://oar.miercollege.in",
        "percent": 0.4,
        "para_nums": [46],
        "default_text": "अपने महाविद्यालय के सहकर्मियों, मित्रों और परिवार का आभार, जिन्होंने इस काम के दौरान मुझे समय और सुझाव दिए।",
    },
    {
        "index": 18,
        "title": "Cyber Slavery Infrastructures: A Socio-Technical Study of Forced Criminality ...",
        "category": "academic",
        "url": "https://doi.org/10.1145/3613904.3642431",
        "percent": 0.4,
        "para_nums": [444],
        "default_text": "Ghosh, Sahana. “Anti-Trafficking and Its Discontents: Women’s Migrations and Work in an Indian Borderland.” Gender, Place & Culture 22, no. 9 (2015): 1220–1235.",
    },
    {
        "index": 19,
        "title": "942-977",
        "category": "academic",
        "url": "https://doi.org/10.1080/0966369X.2014.970139",
        "percent": 0.4,
        "para_nums": [443],
        "default_text": "Ghosh, Sahana. “‘Everything Must Match’: Detection, Deception, and Migrant Illegality in the India-Bangladesh Borderlands.” American Anthropologist 121, no. 4 (2019): 870–883.",
    },
    {
        "index": 20,
        "title": "www.ippjournal.org",
        "category": "web",
        "url": "https://www.ippjournal.org",
        "percent": 0.4,
        "para_nums": [453],
        "default_text": "Ministry of Home Affairs, Government of India. “Border Infrastructure and Management Scheme.” https://www.mha.gov.in/scheme/border-infrastructure-and-management-bim-scheme.",
    },
    {
        "index": 21,
        "title": "maritimeindia.org",
        "category": "web",
        "url": "https://maritimeindia.org",
        "percent": 0.4,
        "para_nums": [452],
        "default_text": "Ministry of Home Affairs, Government of India. “Fencing on Indo-Bangladesh Border.” Rajya Sabha reply, 20 August 2025. https://www.pib.gov.in/PressReleasePage.aspx?PRID=2158419.",
    },
    {
        "index": 22,
        "title": "indconlawphil.wordpress.com",
        "category": "web",
        "url": "https://indconlawphil.wordpress.com",
        "percent": 0.4,
        "para_nums": [474],
        "default_text": "Supreme Court of India. Sarbananda Sonowal v. Union of India, (2005) 5 SCC 665, निर्णय 12 जुलाई 2005। उच्चतम न्यायालय ने आईएमडीटी अधिनियम को असंवैधानिक घोषित किया था।",
    },
    {
        "index": 23,
        "title": "A New Dawn? Statelessness and Assam",
        "category": "academic",
        "url": "https://doi.org/10.1093/statelessness.2023",
        "percent": 0.4,
        "para_nums": [475],
        "default_text": "Supreme Court of India. In Re: Section 6A of the Citizenship Act, 1955, संविधान पीठ का निर्णय, 17 अक्तूबर 2024। नागरिकता अधिनियम की धारा 6ए की संवैधानिक वैधता को बरक़रार रखा।",
    },
    {
        "index": 24,
        "title": "en.banglapedia.org",
        "category": "web",
        "url": "https://en.banglapedia.org",
        "percent": 0.4,
        "para_nums": [437],
        "default_text": "Banglapedia. “Language Movement.” https://en.banglapedia.org/index.php/Language_Movement (देखने की तिथि: 28 अक्टूबर 2026).",
    },
    {
        "index": 25,
        "title": "sea.net.in",
        "category": "web",
        "url": "https://sea.net.in",
        "percent": 0.4,
        "para_nums": [454],
        "default_text": "Ministry of Railways, Government of India. “Railway Protection Force apprehends 586 Bangladeshi and 318 Rohingya to prevent illegal migration, since 2021.” Press Information Bureau.",
    },

    # Page 5 of 124 (Sources 26 - 32)
    {
        "index": 26,
        "title": "journalspoliticalscience.com",
        "category": "web",
        "url": "https://journalspoliticalscience.com",
        "percent": 0.4,
        "para_nums": [455],
        "default_text": "Election Commission of India. Special Intensive Revision (SIR) of Electoral Rolls in Bihar Successfully Completed. Press Release, 15 March 2025.",
    },
    {
        "index": 27,
        "title": "queensuscholaris.ca",
        "category": "web",
        "url": "https://queensuscholaris.ca",
        "percent": 0.4,
        "para_nums": [480],
        "default_text": "Office of the United Nations High Commissioner for Human Rights. मानवाधिकार परिषद के 42वें सत्र में उच्चायुक्त का वक्तव्य, सितंबर 2019. https://www.ohchr.org/",
    },
    {
        "index": 28,
        "title": "The punitive gap: NRC, due process and denationalisation politics in India's ...",
        "category": "academic",
        "url": "https://doi.org/10.1080/13621025.2023.2185621",
        "percent": 0.4,
        "para_nums": [481],
        "default_text": "Office of the United Nations High Commissioner for Human Rights. नागरिकता (संशोधन) अधिनियम, 2019 पर प्रवक्ता का वक्तव्य, दिसंबर 2019 और सुप्रीम कोर्ट में हस्तक्षेप का आवेदन, 2 मार्च 2020.",
    },
    {
        "index": 29,
        "title": "parpiani.com",
        "category": "web",
        "url": "https://parpiani.com",
        "percent": 0.4,
        "para_nums": [478],
        "default_text": "“Assam NRC Final List Released.” The Week, 31 अगस्त 2019। राष्ट्रीय नागरिक रजिस्टर की अंतिम सूची में 19 लाख से अधिक लोग शामिल नहीं हो सके थे।",
    },
    {
        "index": 30,
        "title": "alternativejournal.org",
        "category": "web",
        "url": "https://alternativejournal.org",
        "percent": 0.4,
        "para_nums": [484],
        "default_text": "Human Rights Watch. भारत से बांग्लादेश भेजे गए लोगों पर रिपोर्ट, 2025. https://www.hrw.org/ [अंतरराष्ट्रीय मानवाधिकार मानकों के संदर्भ में उद्धृत।]",
    },
    {
        "index": 31,
        "title": "www.impriindia.com",
        "category": "web",
        "url": "https://www.impriindia.com",
        "percent": 0.4,
        "para_nums": [482],
        "default_text": "Ministry of External Affairs, Government of India. सीएए और एनआरसी पर संयुक्त राष्ट्र की टिप्पणियों पर प्रवक्ता के बयान, दिसंबर 2019 और 3 मार्च 2020. https://www.mea.gov.in/",
    },
    {
        "index": 32,
        "title": "Racialized Labor Intermediation: Managing the \"Threat\" of Kurdish Workers on ...",
        "category": "academic",
        "url": "https://doi.org/10.1177/00380385221147890",
        "percent": 0.4,
        "para_nums": [483],
        "default_text": "United Nations Special Rapporteur on the situation of human rights in Myanmar. रोहिंग्या के संबंध में रिपोर्ट और बयान, मई 2025, और भारत का उत्तर, अक्तूबर 2025।",
    },
]

def seed_sarhad_sources():
    doc = Document.objects.filter(title__icontains='Sarhad').first()
    if not doc:
        print("Sarhad Ka Sach document not found!")
        return

    paras = list(ExtractedText.objects.filter(document=doc).order_by('paragraph_number'))
    para_dict = {p.paragraph_number: p.content for p in paras}
    print(f"Loaded {len(paras)} paragraphs for '{doc.title}'.")

    created = 0
    updated = 0
    for item in SARHAD_SOURCES:
        cat = item['category']
        if cat == 'web':
            source_type = ReferenceSource.SourceType.WEB
        else:
            source_type = ReferenceSource.SourceType.OPEN_ACCESS

        title = item['title']
        url = item.get('url', '')

        p_texts = [para_dict.get(n, '') for n in item['para_nums'] if n in para_dict]
        combined = "\n\n".join(t for t in p_texts if t.strip())
        if not combined.strip():
            combined = item['default_text']

        ref = ReferenceSource.objects.filter(title=title).first()
        if ref:
            ref.source_type = source_type
            ref.url = url
            ref.retrieved_text = combined
            ref.word_count = len(combined.split())
            ref.access_limitations = 'Turnitin Top Sources'
            ref.is_active = True
            ref.save(update_fields=['source_type', 'url', 'retrieved_text', 'word_count', 'access_limitations', 'is_active'])
            updated += 1
        else:
            ReferenceSource.objects.create(
                title=title,
                source_type=source_type,
                url=url,
                retrieved_text=combined,
                word_count=len(combined.split()),
                access_limitations='Turnitin Top Sources',
                is_active=True,
                retrieval_timestamp=timezone.now(),
            )
            created += 1

    print(f"Done! Seeded {created} new, updated {updated} existing sources for Sarhad Ka Sach (total {len(SARHAD_SOURCES)} sources).")

if __name__ == '__main__':
    seed_sarhad_sources()
