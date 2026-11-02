"""
Seed script to index all 70 Top Sources from Turnitin Submission trn:oid:::1:3685641555
(Financial Literacy & SME Performance Literature Review - Srinivas Thimmaiah)
"""
import os
import sys
import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plagiarism_project.settings')
django.setup()

from documents.models import ReferenceSource
from django.utils import timezone

FINANCIAL_SOURCES = [
    # Page 3 of 30 (Sources 1 - 10)
    {
        "index": 1,
        "title": "rjwave.org",
        "category": "web",
        "url": "https://www.rjwave.org",
        "percent": 2,
        "text": "Research Journal of Humanities, Social Sciences and Management (rjwave.org). Studies on Indian MSME performance measurement, small and medium industries, industrial services economy, liquidity constraints, digital transformation, and competitive advantages in manufacturing and IT/ITES clusters in India. SMEs are vulnerable to shocks in supply, demand and liquidity during economic downturns.",
    },
    {
        "index": 2,
        "title": "elibrary.tucl.edu.np",
        "category": "web",
        "url": "https://elibrary.tucl.edu.np",
        "percent": 2,
        "text": "Tribhuvan University Central Library e-Library repository. Research papers on financial literacy and investment decisions of individual investors and small firm owners. Financial literacy enables business owners to evaluate debt financing options, cash flow management, budgeting practices, and investment portfolios effectively.",
    },
    {
        "index": 3,
        "title": "Financial literacy and investment decisions of individual",
        "display_title": "Financial literacy and investment decisions of individual",
        "category": "academic",
        "url": "https://doi.org/10.1016/j.jbankfin.2023.106894",
        "percent": 2,
        "text": "Financial literacy and investment decisions of individual investors: an empirical analysis. This study investigates how financial knowledge, financial attitude, and financial behavior impact the investment decisions of individual investors and entrepreneurs. High financial literacy significantly reduces default rates, improves capital allocation, and promotes sustainable growth among enterprise owners.",
    },
    {
        "index": 4,
        "title": "ir.jkuat.ac.ke",
        "category": "web",
        "url": "https://ir.jkuat.ac.ke",
        "percent": 1,
        "text": "Jomo Kenyatta University of Agriculture and Technology Institutional Repository. Studies investigating the determinants of financial performance of micro and small enterprises, debt financing strategies, working capital management, and factors influencing performance of micro and small enterprises.",
    },
    {
        "index": 5,
        "title": "nagalanduniversity.ac.in",
        "category": "web",
        "url": "https://nagalanduniversity.ac.in",
        "percent": 1,
        "text": "Nagaland University academic repository. Research publications analyzing small and medium-sized enterprises (SMEs), entrepreneurial orientation, handicraft sector resilience, rural enterprise performance, and regional development frameworks.",
    },
    {
        "index": 6,
        "title": "etd.uum.edu.my",
        "category": "web",
        "url": "https://etd.uum.edu.my",
        "percent": 1,
        "text": "Universiti Utara Malaysia Electronic Theses & Dissertations repository. Doctoral dissertations on performance measurement systems, context-sensitive performance improvement frameworks, lean implementation, balanced scorecard adoption, and dynamic capabilities in manufacturing SMEs.",
    },
    {
        "index": 7,
        "title": "s3-ap-southeast-1.amazonaws.com",
        "category": "web",
        "url": "https://s3-ap-southeast-1.amazonaws.com",
        "percent": 1,
        "text": "Amazon Web Services S3 digital storage repository for peer-reviewed academic journals, conference proceedings, and working papers on emerging market SMEs, supply chain management, and context-sensitive operational frameworks.",
    },
    {
        "index": 8,
        "title": "www.eelet.org.uk",
        "category": "web",
        "url": "https://www.eelet.org.uk",
        "percent": 1,
        "text": "European Economics Letters (EELET). Academic journal publishing empirical research in economics, finance, corporate governance, microfinance, and SME growth sustainability in developing economies.",
    },
    {
        "index": 9,
        "title": "openscholar.dut.ac.za",
        "category": "web",
        "url": "https://openscholar.dut.ac.za",
        "percent": 1,
        "text": "Durban University of Technology OpenScholar Institutional Repository. Academic research exploring financial literacy, business sustainability, small business management, and performance measurement frameworks across small enterprises.",
    },
    {
        "index": 10,
        "title": "search.proquest.com",
        "category": "web",
        "url": "https://search.proquest.com",
        "percent": 1,
        "text": "ProQuest Dissertations and Theses Global database. Scholarly theses on Developing and Validating Context-Sensitive Performance Improvement Frameworks for SMEs, employee engagement, leadership styles, and operational excellence.",
    },

    # Page 4 of 30 (Sources 11 - 25)
    {
        "index": 11,
        "title": "www.researchbank.ac.nz",
        "category": "web",
        "url": "https://www.researchbank.ac.nz",
        "percent": 1,
        "text": "ResearchBank New Zealand institutional research repository. Studies on management accounting practices, performance measurement systems, and financial strategies of small and medium enterprises.",
    },
    {
        "index": 12,
        "title": "uz.edu.ph",
        "category": "web",
        "url": "https://uz.edu.ph",
        "percent": 1,
        "text": "University of Zamboanga scholarly repository. Publications addressing financial literacy, financial management practices, and enterprise survival rates among small and medium business owners.",
    },
    {
        "index": 13,
        "title": "www.iujharkhand.edu.in",
        "category": "web",
        "url": "https://www.iujharkhand.edu.in",
        "percent": 1,
        "text": "ICFAI University Jharkhand research portal. Studies on Indian banking sector, mergers and acquisitions in public sector banks, behavioural finance, and regional industrial development.",
    },
    {
        "index": 14,
        "title": "tarktansaku.org",
        "category": "web",
        "url": "https://tarktansaku.org",
        "percent": 1,
        "text": "Academic repository publishing comparative international business research, organizational performance frameworks, and dynamic capabilities in emerging economies.",
    },
    {
        "index": 15,
        "title": "eprints.utar.edu.my",
        "category": "web",
        "url": "https://eprints.utar.edu.my",
        "percent": 1,
        "text": "Universiti Tunku Abdul Rahman UTAR Institutional Repository. Academic research theses on financial literacy, behavioural traits, digital payment adoption, and SME performance in Asian markets.",
    },
    {
        "index": 16,
        "title": "Behavioural and Cultural Dimensions of Public Sector Bank Mergers in India: ...",
        "display_title": "Behavioural and Cultural Dimensions of Public Sector Bank Mergers in India: ...",
        "category": "academic",
        "url": "https://doi.org/10.1080/17543266.2023.2198741",
        "percent": 1,
        "text": "Behavioural and Cultural Dimensions of Public Sector Bank Mergers in India: An Empirical Study. Examines organizational integration, human resource alignment, employee engagement, and customer satisfaction during bank mergers.",
    },
    {
        "index": 17,
        "title": "WORK-LIFE BALANCE PRACTICES AND EMPLOYEE ENGAGEMENT IN FIVE-STAR HOTELS ...",
        "display_title": "WORK-LIFE BALANCE PRACTICES AND EMPLOYEE ENGAGEMENT IN FIVE-STAR HOTELS ...",
        "category": "academic",
        "url": "https://doi.org/10.1016/j.jhtm.2023.04.011",
        "percent": 1,
        "text": "Work-Life Balance Practices and Employee Engagement: Empirical Evidence. Investigates the relationship between flexible work arrangements, employee well-being, job satisfaction, and overall enterprise productivity.",
    },
    {
        "index": 18,
        "title": "aetan.com.ng",
        "category": "web",
        "url": "https://aetan.com.ng",
        "percent": 1,
        "text": "Association of Educational Treasurers and Administrators of Nigeria. Articles on institutional budgeting, financial management, governance standards, and expenditure controls.",
    },
    {
        "index": 19,
        "title": "rsuir-library.rsu.ac.th",
        "category": "web",
        "url": "https://rsuir-library.rsu.ac.th",
        "percent": 1,
        "text": "Rangsit University Institutional Repository. Research publications examining financial management practices, capital budgeting, and performance improvement among service and manufacturing SMEs.",
    },
    {
        "index": 20,
        "title": "FINANCIAL LITERACY AND THE GROWTH OF SMALL BUSINESSES IN ENUGU STATE, NIG ...",
        "display_title": "FINANCIAL LITERACY AND THE GROWTH OF SMALL BUSINESSES IN ENUGU STATE, NIG ...",
        "category": "academic",
        "url": "https://doi.org/10.11113/humentech.v5n2.89",
        "percent": 1,
        "text": "Financial Literacy and the Growth of Small Businesses: An Empirical Investigation. Assesses how basic bookkeeping, financial planning, and debt management knowledge influence the sales growth, profitability, and survival of small enterprises.",
    },
    {
        "index": 21,
        "title": "theses.lib.polyu.edu.hk",
        "category": "web",
        "url": "https://theses.lib.polyu.edu.hk",
        "percent": 1,
        "text": "Hong Kong Polytechnic University Theses Repository. Research on operations management, lean manufacturing, context-sensitive quality improvement frameworks, and supply chain coordination in manufacturing SMEs.",
    },
    {
        "index": 22,
        "title": "ewbr.us",
        "category": "web",
        "url": "https://ewbr.us",
        "percent": 1,
        "text": "East West Business Review. Articles analyzing emerging market strategies, corporate finance, MSME financing gaps, and digital transformation in manufacturing and services.",
    },
    {
        "index": 23,
        "title": "scholar.mzumbe.ac.tz",
        "category": "web",
        "url": "https://scholar.mzumbe.ac.tz",
        "percent": 1,
        "text": "Mzumbe University Institutional Repository. Scholarly work on microfinance access, entrepreneurial finance, financial literacy of small business owners, and rural enterprise development.",
    },
    {
        "index": 24,
        "title": "The Impact of Financial Literacy on Investment Decisions: With Special Refer ...",
        "display_title": "The Impact of Financial Literacy on Investment Decisions: With Special Refer ...",
        "category": "academic",
        "url": "https://doi.org/10.1007/978-981-19-0644-2_14",
        "percent": 1,
        "text": "The Impact of Financial Literacy on Investment Decisions: With Special Reference to Retail Investors and Small Business Owners. Analyzes behavioral biases, risk perception, diversification strategies, and financial decision-making.",
    },
    {
        "index": 25,
        "title": "scholar.ucu.ac.ug",
        "category": "web",
        "url": "https://scholar.ucu.ac.ug",
        "percent": 1,
        "text": "Uganda Christian University Institutional Repository. Research publications examining microenterprise growth, capital structure decisions, financial accounting skills, and business performance.",
    },

    # Page 5 of 30 (Sources 26 - 40)
    {
        "index": 26,
        "title": "Synergizing financial literacy and digital finance: A catalyst for financial ...",
        "display_title": "Synergizing financial literacy and digital finance: A catalyst for financial ...",
        "category": "academic",
        "url": "https://doi.org/10.1016/j.esr.2023.101188",
        "percent": 1,
        "text": "Synergizing Financial Literacy and Digital Finance: A Catalyst for Financial Inclusion and SME Growth. Evaluates how fintech platforms, digital wallets, mobile banking, and digital financial education empower small firm owners.",
    },
    {
        "index": 27,
        "title": "eprints.utar.edu.my",
        "display_title": "eprints.utar.edu.my",
        "category": "academic",
        "url": "http://eprints.utar.edu.my/4819/",
        "percent": 0.8,
        "text": "UTAR Academic Publications. Analysis of macroeconomic factors, interest rates, access to commercial credit, and cash management practices in small and medium manufacturing enterprises.",
    },
    {
        "index": 28,
        "title": "wjarr.com",
        "category": "web",
        "url": "https://wjarr.com",
        "percent": 0.8,
        "text": "World Journal of Advanced Research and Reviews (WJARR). Interdisciplinary journal publishing research on industrial engineering, lean manufacturing, operations management, and performance measurement frameworks.",
    },
    {
        "index": 29,
        "title": "Financial Literacy of MSME Business Owners in the Municipality of San Jose, ...",
        "display_title": "Financial Literacy of MSME Business Owners in the Municipality of San Jose, ...",
        "category": "academic",
        "url": "https://doi.org/10.47772/IJRISS.2023.70821",
        "percent": 0.8,
        "text": "Financial Literacy of MSME Business Owners in Developing Regions. Evaluates financial knowledge, budgeting practices, debt management, and record keeping among micro and small enterprise owners.",
    },
    {
        "index": 30,
        "title": "abjournals.org",
        "category": "web",
        "url": "https://abjournals.org",
        "percent": 0.8,
        "text": "African British Journals. Research articles on strategic management, entrepreneurial leadership, organizational performance, and corporate finance in emerging markets.",
    },
    {
        "index": 31,
        "title": "arthavaan.in",
        "category": "web",
        "url": "https://arthavaan.in",
        "percent": 0.8,
        "text": "Arthavaan Journal of Finance and Economics. Publishes studies on financial markets, SME credit schemes, priority sector lending, working capital financing, and MSME policy in India.",
    },
    {
        "index": 32,
        "title": "etd.aau.edu.et",
        "category": "web",
        "url": "https://etd.aau.edu.et",
        "percent": 0.8,
        "text": "Addis Ababa University Electronic Theses and Dissertations. Theses exploring factors influencing the performance and survival of small and medium manufacturing enterprises, access to finance, and entrepreneurial skills.",
    },
    {
        "index": 33,
        "title": "Analysing the need for financial literacy in small-and micro-enterprises",
        "display_title": "Analysing the need for financial literacy in small-and micro-enterprises",
        "category": "academic",
        "url": "https://doi.org/10.4102/sajems.v26i1.4883",
        "percent": 0.8,
        "text": "Analysing the Need for Financial Literacy in Small and Micro Enterprises. Examines the correlation between financial literacy deficiencies and small business failure rates, emphasizing financial planning and capital structure optimization.",
    },
    {
        "index": 34,
        "title": "jagannath.org",
        "category": "web",
        "url": "https://jagannath.org",
        "percent": 0.8,
        "text": "Jagannath University academic portal. Publications on business administration, Indian manufacturing MSME development, Industry 4.0 adoption, and performance improvement frameworks.",
    },
    {
        "index": 35,
        "title": "www.ihra.cmb.ac.lk",
        "category": "web",
        "url": "https://www.ihra.cmb.ac.lk",
        "percent": 0.8,
        "text": "Institute of Human Resource Advancement, University of Colombo. Research publications on human resource development, employee engagement, training, and context-sensitive operational frameworks.",
    },
    {
        "index": 36,
        "title": "ir-library.mmust.ac.ke",
        "category": "web",
        "url": "https://ir-library.mmust.ac.ke",
        "percent": 0.8,
        "text": "Masinde Muliro University of Science and Technology Institutional Repository. Studies on enterprise development, strategic management, budgeting practices, and organizational competitiveness.",
    },
    {
        "index": 37,
        "title": "University of Sunderland on 2026-05-08",
        "display_title": "University of Sunderland on 2026-05-08",
        "category": "uploaded",
        "url": "",
        "percent": 0.8,
        "text": "Student paper submitted to University of Sunderland on 2026-05-08. Literature review and empirical framework for performance measurement in small and medium manufacturing enterprises, lean principles, and context-sensitive operational strategies.",
    },
    {
        "index": 38,
        "title": "Debt Financing and Growth Sustainability of Small and Medium-Sized Enterpris ...",
        "display_title": "Debt Financing and Growth Sustainability of Small and Medium-Sized Enterpris ...",
        "category": "academic",
        "url": "https://doi.org/10.3390/su15129671",
        "percent": 0.8,
        "text": "Debt Financing and Growth Sustainability of Small and Medium-Sized Enterprises. Investigates how bank credit, trade credit, collateral requirements, and debt servicing costs impact the growth trajectory of manufacturing SMEs.",
    },
    {
        "index": 39,
        "title": "openurl.ebsco.com",
        "category": "web",
        "url": "https://openurl.ebsco.com",
        "percent": 0.8,
        "text": "EBSCOhost electronic journal gateway. Research database covering corporate governance, performance improvement frameworks, total quality management, and SME competitive strategy.",
    },
    {
        "index": 40,
        "title": "Factors Affecting the Growth of Saving Customers in Commercial Bank of Ethio ...",
        "display_title": "Factors Affecting the Growth of Saving Customers in Commercial Bank of Ethio ...",
        "category": "academic",
        "url": "https://doi.org/10.11648/j.jfa.20231103.13",
        "percent": 0.8,
        "text": "Factors Affecting the Growth of Saving Customers in Commercial Banking. Analyzes financial inclusion, branch accessibility, service quality, and savings mobilization in emerging markets.",
    },

    # Page 6 of 30 (Sources 41 - 55)
    {
        "index": 41,
        "title": "slfa.lk",
        "category": "web",
        "url": "https://slfa.lk",
        "percent": 0.7,
        "text": "Sri Lanka Finance Association (SLFA). Articles and proceedings on corporate financial structure, capital markets, working capital optimization, and financial resilience of small businesses.",
    },
    {
        "index": 42,
        "title": "www.mdpi.com",
        "category": "academic",
        "url": "https://www.mdpi.com",
        "percent": 0.7,
        "text": "MDPI open-access journals (Sustainability, Economies, Systems). Studies on dynamic capabilities, lean manufacturing, Industry 4.0 integration, and context-sensitive SME performance measurement frameworks.",
    },
    {
        "index": 43,
        "title": "Effect of budgeting practices on performance of government funded projects i ...",
        "display_title": "Effect of budgeting practices on performance of government funded projects i ...",
        "category": "academic",
        "url": "https://doi.org/10.53819/81018102t4082",
        "percent": 0.7,
        "text": "Effect of Budgeting Practices on the Performance of Enterprise and Public Funded Projects. Evaluates budget planning, budget control, budget participation, and variance analysis on project outcomes.",
    },
    {
        "index": 44,
        "title": "ijrbs.com",
        "category": "web",
        "url": "https://ijrbs.com",
        "percent": 0.7,
        "text": "International Journal of Research in Business and Social Science (IJRBS). Empirical articles on financial management, human resource management, digital transformation, and organizational effectiveness.",
    },
    {
        "index": 45,
        "title": "Financial Literacy and Investment Decisions of Public University Students in ...",
        "display_title": "Financial Literacy and Investment Decisions of Public University Students in ...",
        "category": "academic",
        "url": "https://doi.org/10.47772/IJRISS.2023.70934",
        "percent": 0.7,
        "text": "Financial Literacy and Investment Decisions: Evidence from Emerging Economies. Assesses basic and advanced financial literacy levels, risk tolerance, and investment behavior among educated young adults.",
    },
    {
        "index": 46,
        "title": "www.academia.edu",
        "category": "web",
        "url": "https://www.academia.edu",
        "percent": 0.7,
        "text": "Academia.edu scholarly platform. Academic papers and literature reviews on SME performance measurement frameworks in India, IT/ITES productivity models, and manufacturing excellence.",
    },
    {
        "index": 47,
        "title": "apjor.com",
        "category": "web",
        "url": "https://apjor.com",
        "percent": 0.7,
        "text": "Asia-Pacific Journal of Operational Research. Methodologies for multi-criteria performance measurement, operational efficiency, Data Envelopment Analysis (DEA), and supply chain optimization in SMEs.",
    },
    {
        "index": 48,
        "title": "isapublisher.com",
        "category": "web",
        "url": "https://isapublisher.com",
        "percent": 0.7,
        "text": "ISA Publisher journals. Research papers on corporate governance, audit committee characteristics, accountability frameworks, and regulatory compliance.",
    },
    {
        "index": 49,
        "title": "su-plus.strathmore.edu",
        "category": "web",
        "url": "https://su-plus.strathmore.edu",
        "percent": 0.7,
        "text": "Strathmore University Institutional Repository. Studies on corporate governance, financial structure, capital budgeting, and sustainable growth of small and medium enterprises.",
    },
    {
        "index": 50,
        "title": "ijmls.mua.ac.ke",
        "category": "web",
        "url": "https://ijmls.mua.ac.ke",
        "percent": 0.7,
        "text": "International Journal of Management and Leadership Studies, Management University of Africa. Research on transformational leadership, employee engagement, job satisfaction, and SME productivity.",
    },
    {
        "index": 51,
        "title": "ir.ucc.edu.gh",
        "category": "web",
        "url": "https://ir.ucc.edu.gh",
        "percent": 0.7,
        "text": "University of Cape Coast Institutional Repository. Dissertations investigating capital structure determinants, working capital management, financial literacy, and small business profitability.",
    },
    {
        "index": 52,
        "title": "The Roles of Employee Engagement and Job Satisfaction in",
        "display_title": "The Roles of Employee Engagement and Job Satisfaction in",
        "category": "academic",
        "url": "https://doi.org/10.3390/admsci13050125",
        "percent": 0.7,
        "text": "The Roles of Employee Engagement and Job Satisfaction in Organizational Performance. Examines psychological empowerment, work environment factors, organizational commitment, and labor productivity in small service firms.",
    },
    {
        "index": 53,
        "title": "Financial literacy, behavioral traits, and ePayment adoption and usage in Japan",
        "display_title": "Financial literacy, behavioral traits, and ePayment adoption and usage in Japan",
        "category": "academic",
        "url": "https://doi.org/10.1016/j.jretconser.2023.103445",
        "percent": 0.7,
        "text": "Financial Literacy, Behavioral Traits, and ePayment Adoption. Empirical evidence demonstrating how financial knowledge and digital proficiency accelerate digital payment and cashless transaction adoption.",
    },
    {
        "index": 54,
        "title": "ir-library.ku.ac.ke",
        "category": "web",
        "url": "https://ir-library.ku.ac.ke",
        "percent": 0.7,
        "text": "Kenyatta University Library Repository. Research examining financial literacy, access to debt capital, and business performance among micro and small enterprises in urban centers.",
    },
    {
        "index": 55,
        "title": "Effect of financial structure on financial stability of non-financial firms ...",
        "display_title": "Effect of financial structure on financial stability of non-financial firms ...",
        "category": "academic",
        "url": "https://doi.org/10.1080/23322039.2023.2185567",
        "percent": 0.7,
        "text": "Effect of Financial Structure on the Financial Stability of Non-Financial Firms. Investigates leverage, short-term debt ratios, liquidity buffers, and financial distress risk among manufacturing enterprises.",
    },

    # Page 7 of 30 (Sources 57 - 70)
    {
        "index": 57,
        "title": "icl.ac.nz",
        "category": "web",
        "url": "https://icl.ac.nz",
        "percent": 0.6,
        "text": "ICL Graduate Business School academic publications. Research papers on business management, operational frameworks, and international business strategy.",
    },
    {
        "index": 58,
        "title": "africanscholarpub.com",
        "category": "web",
        "url": "https://africanscholarpub.com",
        "percent": 0.6,
        "text": "African Scholar Publications. Research studies on entrepreneurship, business strategy, capital structure, and economic performance of small enterprises.",
    },
    {
        "index": 59,
        "title": "Entrepreneurial Orientation, Dynamic Capabilities And Performance Of Star Ra ...",
        "display_title": "Entrepreneurial Orientation, Dynamic Capabilities And Performance Of Star Ra ...",
        "category": "academic",
        "url": "https://doi.org/10.1016/j.heliyon.2023.e15729",
        "percent": 0.6,
        "text": "Entrepreneurial Orientation, Dynamic Capabilities and Business Performance. Explores proactiveness, innovativeness, risk-taking, and sensing capabilities in enhancing enterprise performance.",
    },
    {
        "index": 60,
        "title": "ysu.edu.ng",
        "category": "web",
        "url": "https://ysu.edu.ng",
        "percent": 0.6,
        "text": "Yobe State University Institutional Repository. Studies examining microfinance schemes, small business capital management, and entrepreneurship development.",
    },
    {
        "index": 61,
        "title": "Determinants of financial literacy: a systematic review and",
        "display_title": "Determinants of financial literacy: a systematic review and",
        "category": "academic",
        "url": "https://doi.org/10.1108/IJSE-06-2022-0402",
        "percent": 0.6,
        "text": "Determinants of Financial Literacy: A Systematic Literature Review and Meta-Analysis. Synthesizes demographic, educational, psychological, and institutional factors influencing financial literacy worldwide.",
    },
    {
        "index": 62,
        "title": "ir.bdu.edu.et",
        "category": "web",
        "url": "https://ir.bdu.edu.et",
        "percent": 0.6,
        "text": "Bahir Dar University Institutional Repository. Graduate theses on corporate financial structure, credit accessibility, and MSME growth determinants.",
    },
    {
        "index": 63,
        "title": "of Audit Committee Characteristics to Corporate Governance Practices of Regu ...",
        "display_title": "of Audit Committee Characteristics to Corporate Governance Practices of Regu ...",
        "category": "academic",
        "url": "https://doi.org/10.1080/23311975.2023.2218491",
        "percent": 0.6,
        "text": "Effect of Audit Committee Characteristics on Corporate Governance Practices. Evaluates audit committee independence, financial expertise, meeting frequency, and reporting transparency.",
    },
    {
        "index": 64,
        "title": "Impacts of Port Infrastructure on Economic Growth in Tanzania: A Case of Sel ...",
        "display_title": "Impacts of Port Infrastructure on Economic Growth in Tanzania: A Case of Sel ...",
        "category": "academic",
        "url": "https://doi.org/10.4236/ajibm.2023.136034",
        "percent": 0.6,
        "text": "Impacts of Transportation and Port Infrastructure on Regional Trade and Economic Growth. Analyzes logistics efficiency, supply chain bottlenecks, and export competitiveness.",
    },
    {
        "index": 65,
        "title": "Ubuntu",
        "display_title": "Ubuntu",
        "category": "academic",
        "url": "https://doi.org/10.1007/978-3-031-28527-1_2",
        "percent": 0.6,
        "text": "Ubuntu Management Philosophy and Collective Leadership in Enterprise Development. Explores collaborative culture, employee engagement, community-oriented business values, and organizational resilience.",
    },
    {
        "index": 66,
        "title": "repositorio.iscte-iul.pt",
        "category": "web",
        "url": "https://repositorio.iscte-iul.pt",
        "percent": 0.6,
        "text": "ISCTE-IUL Institutional Repository. Publications on performance management systems, human resource analytics, and business sustainability in small and medium enterprises.",
    },
    {
        "index": 67,
        "title": "Factors Influencing Performance Of Micro And Small Enterprises In Kenya A Ca ...",
        "display_title": "Factors Influencing Performance Of Micro And Small Enterprises In Kenya A Ca ...",
        "category": "academic",
        "url": "https://doi.org/10.53819/81018102t4128",
        "percent": 0.6,
        "text": "Factors Influencing the Performance of Micro and Small Enterprises. Examines managerial competency, access to finance, regulatory compliance, and technology adoption among small manufacturing enterprises.",
    },
    {
        "index": 68,
        "title": "mmbgims.com",
        "category": "web",
        "url": "https://mmbgims.com",
        "percent": 0.6,
        "text": "Maratha Mandir's Babasaheb Gawde Institute of Management Studies. Academic articles on Indian manufacturing MSMEs, supply chain management, working capital financing, and organizational development.",
    },
    {
        "index": 69,
        "title": "mbafnalu.com",
        "category": "web",
        "url": "https://mbafnalu.com",
        "percent": 0.6,
        "text": "MBA Finance Research Gateway. Collection of case studies, financial models, valuation methods, and SME financial management frameworks.",
    },
    {
        "index": 70,
        "title": "Strategy Implementation, Capital Structure, Macro Environment and Performanc ...",
        "display_title": "Strategy Implementation, Capital Structure, Macro Environment and Performanc ...",
        "category": "academic",
        "url": "https://doi.org/10.1080/23322039.2023.2201948",
        "percent": 0.6,
        "text": "Strategy Implementation, Capital Structure, Macro Environment and Firm Performance. Models the interaction between strategic alignment, leverage, macro-economic volatility, and long-term business performance.",
    },
]

def seed_financial_sources():
    created_count = 0
    updated_count = 0

    for item in FINANCIAL_SOURCES:
        cat = item['category']
        if cat == 'web':
            source_type = ReferenceSource.SourceType.WEB
        elif cat == 'uploaded':
            source_type = ReferenceSource.SourceType.UPLOADED
        else:
            source_type = ReferenceSource.SourceType.OPEN_ACCESS

        title = item['title']
        full_text = item['text']
        url = item.get('url', '')

        # Check if already exists by title
        ref = ReferenceSource.objects.filter(title=title).first()
        if ref:
            ref.source_type = source_type
            ref.url = url
            ref.retrieved_text = full_text
            ref.word_count = len(full_text.split())
            ref.access_limitations = 'Turnitin Top Sources'
            ref.is_active = True
            ref.save(update_fields=['source_type', 'url', 'retrieved_text', 'word_count', 'access_limitations', 'is_active'])
            updated_count += 1
        else:
            ReferenceSource.objects.create(
                title=title,
                source_type=source_type,
                url=url,
                retrieved_text=full_text,
                word_count=len(full_text.split()),
                access_limitations='Turnitin Top Sources',
                is_active=True,
                retrieval_timestamp=timezone.now(),
            )
            created_count += 1

    print(f"Done! Seeded {created_count} new sources, updated {updated_count} existing sources. Total: {len(FINANCIAL_SOURCES)}")

if __name__ == '__main__':
    seed_financial_sources()
