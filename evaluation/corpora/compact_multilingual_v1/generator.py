"""Build the fully fictional compact-multilingual-v1 benchmark corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.evaluation.models import EvaluationDataset, EvaluationCase
from app.services.evaluation.synthetic_corpus import corpus_fingerprint


CORPUS_VERSION = "compact-multilingual-v1"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "compact-multilingual-v1"

# Each family deliberately has similar policy subjects and different rules.
# The 40 source documents are fictional; no company, person, or customer data is used.
FAMILIES: tuple[dict[str, Any], ...] = (
    {
        "id": "hr-leave",
        "category": "hr",
        "topics": (
            ("en", "Annual leave carry-over", "unused vacation moved into a new leave year", "kullanılmayan iznin yeni izin yılına devredilmesi", "Team members may carry up to 6 days of unused annual leave into the next leave year. Any balance above the allowance expires on 31 March.", "6 days"),
            ("en", "Sick leave notification", "reporting an absence caused by illness", "hastalık nedeniyle işe gelememe bildirimi", "Employees should notify their team lead at least 4 hours before a shift begins. A medical note is required after 2 consecutive workdays.", "4 hours"),
            ("tr", "Ebeveyn izni süresi", "the length of parental leave", "ebeveyn izninin süresi", "Çalışanlara toplam 18 hafta ebeveyn izni verilir. Bu sürenin en fazla 8 haftası doğumdan önce, kalan kısmı doğumdan sonra kullanılabilir.", "18 hafta"),
            ("tr", "Uzaktan çalışma günleri", "the weekly remote-work allowance", "haftalık uzaktan çalışma hakkı", "Ekip üyeleri haftada en fazla 3 gün uzaktan çalışabilir. Bu düzen için yöneticinin önceden onayı gerekir.", "3 gün"),
        ),
    },
    {
        "id": "identity-security",
        "category": "security",
        "topics": (
            ("en", "API access-token lifetime", "how long a personal API token remains valid", "kişisel API erişim belirtecinin geçerlilik süresi", "A personal API access token remains valid for 90 days from issuance. The owner must create a replacement before the current token expires.", "90 days"),
            ("en", "Browser session timeout", "when an inactive browser session expires", "etkin olmayan tarayıcı oturumunun sona erme süresi", "An inactive browser session expires after 30 minutes. A signed-in session also has an absolute lifetime of 8 hours.", "30 minutes"),
            ("tr", "Çok faktörlü doğrulama aralığı", "how often a managed device must re-check identity", "yönetilen cihazda kimliğin yeniden doğrulanma aralığı", "Yönetilen cihazlarda çok faktörlü kimlik doğrulama en geç 12 saatte bir yeniden istenir. Hassas işlem başlatıldığında bu süre beklenmez.", "12 saatte bir"),
            ("tr", "Hesap kilidi eşiği", "the failed sign-in threshold before a lock", "hesabın kilitlenmesine yol açan hatalı giriş eşiği", "Bir hesap art arda 5 hatalı girişten sonra kilitlenir. Otomatik kilit 20 dakika sürer ve süre sonunda yeniden giriş denenebilir.", "5 hatalı giriş"),
        ),
    },
    {
        "id": "records-retention",
        "category": "operations",
        "topics": (
            ("en", "Personnel-file retention", "how long personnel records are kept after departure", "personel kayıtlarının ayrılıktan sonra saklanma süresi", "Personnel files are retained for 7 years after an employee leaves. The retention clock starts on the recorded separation date.", "7 years"),
            ("en", "Audit-log retention", "how long security audit events remain searchable", "güvenlik denetim kayıtlarının aranabilir kalma süresi", "Security audit events remain searchable for 400 days after creation. Archived copies may be kept separately for investigations.", "400 days"),
            ("tr", "Yedek anlık görüntü saklama", "how long backup snapshots are retained", "yedek anlık görüntülerinin saklanma süresi", "Yedek anlık görüntüleri oluşturulma tarihinden itibaren 45 gün saklanır. Süre dolduğunda eski görüntüler otomatik olarak temizlenir.", "45 gün"),
            ("tr", "Silinen belge bekletme süresi", "how long a deleted file stays recoverable", "silinen dosyanın geri alınabilir kalma süresi", "Silinen belgeler geri dönüşüm alanında 30 gün tutulur. Bu sürenin sonunda belge kalıcı olarak kaldırılır.", "30 gün"),
        ),
    },
    {
        "id": "backup-recovery",
        "category": "operations",
        "topics": (
            ("en", "Full-backup schedule", "the recurring schedule for a complete backup", "tam yedeklemenin yinelenen takvimi", "A complete system backup runs every Sunday at 02:00 UTC. The schedule covers the shared application data volume.", "Sunday at 02:00 UTC"),
            ("en", "Restore-test interval", "how often a recovery restore is tested", "kurtarma geri yüklemesinin test edilme aralığı", "The operations team performs a recovery restore test every 90 days. Each test records the restored dataset and elapsed recovery time.", "90 days"),
            ("tr", "Artımlı yedekleme sıklığı", "the interval between incremental backups", "artımlı yedeklemeler arasındaki süre", "Artımlı yedekleme işleri 6 saatte bir çalışır. Her çalışma son başarılı temel yedekten sonraki değişiklikleri kapsar.", "6 saatte bir"),
            ("tr", "Portal kurtarma hedefi", "the recovery-time objective for the internal portal", "kurum içi portalın kurtarma süresi hedefi", "Kurum içi portal için hedeflenen en uzun kurtarma süresi 4 saattir. Olay yöneticisi bu hedefi kesinti kaydında izler.", "4 saat"),
        ),
    },
    {
        "id": "purchasing-travel",
        "category": "policy",
        "topics": (
            ("en", "Purchase approval threshold", "the spend level that requires purchase approval", "satın alma onayı gerektiren harcama eşiği", "A purchase request above $2,500 requires approval from a department manager before an order is placed.", "$2,500"),
            ("en", "Expense receipt deadline", "the time allowed to submit travel receipts", "seyahat fişlerini teslim etmek için tanınan süre", "Employees must submit travel receipts within 10 business days after returning. Late submissions need an explanation from the budget owner.", "10 business days"),
            ("tr", "Günlük yemek ödeneği", "the daily meal allowance on approved travel", "onaylı seyahatte günlük yemek ödeneği", "Onaylı yurt dışı seyahatlerde günlük yemek ödeneği 45 avrodur. Bu tutara alkollü içecekler dahil değildir.", "45 avro"),
            ("tr", "Otel gecelik üst sınırı", "the nightly hotel reimbursement cap", "otel masrafı için gecelik geri ödeme üst sınırı", "Otel konaklaması için geri ödeme gecelik en fazla 160 avrodur. Daha yüksek bir tutar için seyahatten önce finans onayı alınmalıdır.", "160 avro"),
        ),
    },
    {
        "id": "vendor-finance",
        "category": "policy",
        "topics": (
            ("en", "Supplier security-review renewal", "how often an active supplier is reviewed", "aktif tedarikçinin incelenme sıklığı", "An active supplier receives a security review once every 12 months. A material service change triggers an additional review.", "12 months"),
            ("en", "Software subscription approval", "the annual software spend needing finance approval", "finans onayı gereken yıllık yazılım harcaması", "A software subscription costing more than $1,200 per year needs finance approval before renewal.", "$1,200 per year"),
            ("tr", "Fatura ödeme vadesi", "the standard payment term for a valid invoice", "geçerli bir fatura için standart ödeme vadesi", "Eksiksiz ve onaylı bir tedarikçi faturası, kayıt tarihinden itibaren 30 gün içinde ödenir.", "30 gün"),
            ("tr", "Teklif toplama eşiği", "the purchase value that requires three quotations", "üç teklif gerektiren satın alma tutarı", "50.000 TL üzerindeki ekipman alımlarında karar verilmeden önce en az 3 yazılı teklif toplanır.", "50.000 TL"),
        ),
    },
    {
        "id": "support-response",
        "category": "support",
        "topics": (
            ("en", "Priority-one first response", "the initial response target for a critical incident", "kritik olay için ilk yanıt hedefi", "A priority-one incident receives an initial human response within 15 minutes, around the clock.", "15 minutes"),
            ("en", "Priority-two first response", "the initial response target for a high-impact issue", "yüksek etkili sorun için ilk yanıt hedefi", "A priority-two support case receives an initial response within 4 hours during staffed service hours.", "4 hours"),
            ("tr", "Destek eskalasyon eşiği", "the number of failed attempts before escalation", "eskalasyon öncesindeki başarısız deneme sayısı", "Destek uzmanı aynı çözüm adımını 2 kez uygulayıp sonuç alamazsa kaydı ikinci seviye ekibe aktarır.", "2 kez"),
            ("tr", "Kritik olay bilgilendirme aralığı", "how frequently customers receive a critical-incident update", "kritik olayda müşteriye bilgi verme aralığı", "Öncelik bir olayda destek ekibi müşteriye en geç her 60 dakikada bir durum güncellemesi gönderir.", "60 dakikada bir"),
        ),
    },
    {
        "id": "api-limits",
        "category": "technical",
        "topics": (
            ("en", "API page-size limit", "the largest page a list request may return", "liste isteğinin döndürebileceği en büyük sayfa", "A list endpoint returns at most 100 records in one page. Clients should follow the continuation cursor for later records.", "100 records"),
            ("en", "Rate-limit retry budget", "the retry limit after a rate-limit response", "hız sınırı yanıtından sonraki yeniden deneme sınırı", "After an HTTP 429 response, a client may retry at most 3 times with exponential backoff.", "3 times"),
            ("tr", "Dakikalık API istek kotası", "the number of requests allowed each minute", "her dakika izin verilen istek sayısı", "Standart bir API istemcisi dakikada en fazla 120 istek gönderebilir. Kota her kayan dakika penceresinde yeniden hesaplanır.", "120 istek"),
            ("tr", "API sürüm kaldırma bildirimi", "the notice period before an API version is retired", "API sürümü kaldırılmadan önceki bildirim süresi", "Bir API sürümü kullanımdan kaldırılmadan en az 180 gün önce duyuru yapılır.", "180 gün"),
        ),
    },
    {
        "id": "workstation-operations",
        "category": "security",
        "topics": (
            ("en", "Critical patch deadline", "the deployment window for a critical security patch", "kritik güvenlik yamasının dağıtım süresi", "A critical security patch must be deployed within 72 hours after validation.", "72 hours"),
            ("en", "Routine maintenance window", "the weekly window reserved for planned maintenance", "planlı bakım için ayrılan haftalık zaman aralığı", "Routine maintenance is scheduled on Tuesday between 20:00 and 22:00 UTC.", "Tuesday between 20:00 and 22:00 UTC"),
            ("tr", "İş istasyonu disk şifreleme", "the required encryption strength for a developer laptop", "geliştirici dizüstü bilgisayarı için gereken şifreleme gücü", "Geliştirici iş istasyonlarının diskleri AES-256 ile şifrelenmelidir. Şifreleme durumu cihaz envanterinde denetlenir.", "AES-256"),
            ("tr", "Yedek anahtar yenileme", "how often an archived-backup encryption key is rotated", "arşiv yedeği şifreleme anahtarının yenilenme sıklığı", "Arşiv yedeklerinin şifreleme anahtarları 180 günde bir yenilenir ve eski anahtarlar güvenli biçimde devre dışı bırakılır.", "180 günde bir"),
        ),
    },
    {
        "id": "privacy-requests",
        "category": "security",
        "topics": (
            ("en", "Account recovery-code lifetime", "how long a one-time recovery code can be used", "tek kullanımlık kurtarma kodunun kullanılabileceği süre", "A one-time account recovery code expires 15 minutes after it is issued.", "15 minutes"),
            ("en", "Inactive employee account", "the inactivity period before an account is suspended", "hesabın askıya alınmasından önceki etkin olmama süresi", "An employee account is suspended after 60 days without an interactive sign-in.", "60 days"),
            ("tr", "Veri silme talebi takvimi", "the completion target for a verified deletion request", "doğrulanmış silme talebinin tamamlanma hedefi", "Doğrulanmış bir kişisel veri silme talebi en geç 14 gün içinde tamamlanır.", "14 gün"),
            ("tr", "Veri dışa aktarım bağlantısı", "how long a prepared data export remains downloadable", "hazırlanan veri dışa aktarımının indirilebilir kalma süresi", "Hazırlanan veri dışa aktarım bağlantısı 7 gün boyunca kullanılabilir; süre sonunda dosya otomatik kaldırılır.", "7 gün"),
        ),
    },
    {
        "id": "travel-policy-versions",
        "category": "policy",
        "topics": (
            ("en", "Travel meal allowance — 2024 handbook", "the archived 2024 daily meal allowance", "2024 el kitabındaki günlük yemek ödeneği", "The archived 2024 travel handbook set the meal allowance at $40 per day. This historical rule applied only to trips approved under that edition.", "$40 per day"),
            ("en", "Travel meal allowance — 2025 handbook", "the current 2025 daily meal allowance", "2025 el kitabındaki güncel günlük yemek ödeneği", "The current 2025 travel handbook sets the meal allowance at $45 per day. New trip approvals follow this edition.", "$45 per day"),
            ("tr", "Otel gecelik üst sınırı — 2024 kuralı", "the archived 2024 nightly hotel cap", "2024 kuralındaki gecelik otel üst sınırı", "Arşivlenmiş 2024 seyahat kuralında otel geri ödemesi gecelik en fazla 140 avroydu. Bu eski tutar yalnızca o sürümle onaylanan seyahatlerde geçerliydi.", "140 avro"),
            ("tr", "Otel gecelik üst sınırı — 2025 kuralı", "the current 2025 nightly hotel cap", "2025 kuralındaki güncel gecelik otel üst sınırı", "Güncel 2025 seyahat kuralında otel geri ödemesi gecelik en fazla 160 avrodur. Yeni seyahat onaylarında bu sürüm uygulanır.", "160 avro"),
        ),
    },
)

NO_ANSWER_QUESTIONS = {
    "en": (
        ("What is the annual paid volunteer-day allowance?", "hr-leave"),
        ("Which payroll date is used for a one-time bonus adjustment?", "vendor-finance"),
        ("How many personal guest passes can an employee request each month?", "hr-leave"),
        ("What is the permitted budget for office celebration gifts?", "purchasing-travel"),
        ("How long is the grace period for renewing an expired API token?", "identity-security"),
        ("Which weekday is reserved for the quarterly all-hands meeting?", "workstation-operations"),
        ("What is the reimbursement limit for home-office furniture?", "purchasing-travel"),
        ("How many days of bereavement leave are granted for a cousin?", "hr-leave"),
        ("What is the maximum number of support tickets one person may open?", "support-response"),
        ("Which checksum algorithm is required for customer exports?", "privacy-requests"),
        ("How many sandbox environments does each supplier receive?", "vendor-finance"),
        ("What is the service-credit percentage for a delayed API release?", "api-limits"),
    ),
    "tr": (
        ("Yıllık ücretli gönüllülük izni kaç gündür?", "hr-leave"),
        ("Tek seferlik prim için bordro kesim tarihi nedir?", "vendor-finance"),
        ("Bir çalışan ayda kaç kişisel misafir kartı isteyebilir?", "hr-leave"),
        ("Ofis kutlaması hediyeleri için izin verilen bütçe nedir?", "purchasing-travel"),
        ("Süresi dolmuş API belirtecini yenilemek için tanınan ek süre ne kadardır?", "identity-security"),
        ("Üç aylık şirket toplantısı haftanın hangi günü yapılır?", "workstation-operations"),
        ("Ev-ofis mobilyası için geri ödeme üst sınırı nedir?", "purchasing-travel"),
        ("Kuzen vefatında kaç gün mazeret izni verilir?", "hr-leave"),
        ("Bir kişinin açabileceği en fazla destek kaydı sayısı nedir?", "support-response"),
        ("Müşteri dışa aktarımlarında hangi özet algoritması zorunludur?", "privacy-requests"),
        ("Her tedarikçiye kaç test ortamı verilir?", "vendor-finance"),
        ("Geciken API sürümü için hizmet kredisi yüzdesi nedir?", "api-limits"),
    ),
}


def build_corpus() -> tuple[dict[str, Any], EvaluationDataset, dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    cases: list[EvaluationCase] = []
    family_document_ids: dict[str, list[int]] = {}
    topic_document_ids: list[tuple[dict[str, Any], int]] = []
    next_document_id = 1

    for family in FAMILIES:
        family_ids: list[int] = []
        for language, title, seed_en, seed_tr, text, fact in family["topics"]:
            document_id = next_document_id
            next_document_id += 1
            family_ids.append(document_id)
            topic_document_ids.append(({
                "family": family,
                "language": language,
                "title": title,
                "seed_en": seed_en,
                "seed_tr": seed_tr,
                "text": text,
                "fact": fact,
            }, document_id))
            documents.append({
                "document_id": document_id,
                "filename": f"synthetic-{family['id']}-{document_id:02d}.md",
                "language": language,
                "knowledge_base_ids": [1],
                "text": f"{title}. {text}",
            })
        family_document_ids[family["id"]] = family_ids

    for topic, document_id in topic_document_ids:
        family = topic["family"]
        sibling_ids = [value for value in family_document_ids[family["id"]] if value != document_id]
        for query_language, variant, case_type in (
            (topic["language"], 1, "normal"),
            (topic["language"], 2, "hard_negative"),
            ("tr" if topic["language"] == "en" else "en", 1, "normal"),
        ):
            seed = topic[f"seed_{query_language}"]
            if query_language == "en":
                question = (
                    f"What limit applies to {seed}?" if variant == 1 else
                    f"What number or time window should staff remember for {seed}?"
                )
            else:
                question = (
                    f"{seed.capitalize()} için hangi sayısal sınır uygulanır?" if variant == 1 else
                    f"{seed.capitalize()} konusunda hangi sayı veya süre dikkate alınmalı?"
                )
            cases.append(EvaluationCase(
                id=f"answer-{document_id:02d}-{query_language}-{variant}",
                category=family["category"],
                question=question,
                knowledge_base_ids=[1],
                case_type=case_type,
                language=query_language,
                scenario_id=f"{family['id']}-document-{document_id:02d}",
                expected_document_ids=[document_id],
                expected_facts=[topic["fact"]],
                confusable_document_ids=sibling_ids,
                top_k=3,
            ))

    for language, question_values in NO_ANSWER_QUESTIONS.items():
        for index, (question, family_id) in enumerate(question_values, start=1):
            cases.append(EvaluationCase(
                id=f"no-answer-{language}-{index:02d}",
                category="general" if family_id in {"hr-leave", "purchasing-travel"} else "technical",
                question=question,
                knowledge_base_ids=[1],
                case_type="no_answer",
                language=language,
                scenario_id=f"absent-evidence-{family_id}-{index:02d}",
                expect_answer=False,
                confusable_document_ids=family_document_ids[family_id],
                top_k=3,
            ))

    dataset = EvaluationDataset(
        version=1,
        name=CORPUS_VERSION,
        cases=cases,
    )
    documents_payload = {"corpus_version": CORPUS_VERSION, "documents": documents}
    fingerprint = corpus_fingerprint(CORPUS_VERSION, dataset, documents)
    manifest = {
        "corpus_version": CORPUS_VERSION,
        "fingerprint_sha256": fingerprint,
        "document_count": len(documents),
        "case_count": len(cases),
        "answerable_case_count": sum(case.expect_answer for case in cases),
        "no_answer_case_count": sum(case.case_type == "no_answer" for case in cases),
        "case_type_counts": {
            case_type: sum(case.case_type == case_type for case in cases)
            for case_type in ("normal", "hard_negative", "no_answer")
        },
        "language_counts": {
            language: sum(case.language == language for case in cases)
            for language in ("en", "tr")
        },
        "answerable_language_counts": {
            language: sum(case.language == language and case.expect_answer for case in cases)
            for language in ("en", "tr")
        },
        "cross_language_case_counts": {
            "tr_query_to_en_document": sum(
                case.language == "tr" and case.expect_answer and
                next(doc["language"] for doc in documents if doc["document_id"] == case.expected_document_ids[0]) == "en"
                for case in cases
            ),
            "en_query_to_tr_document": sum(
                case.language == "en" and case.expect_answer and
                next(doc["language"] for doc in documents if doc["document_id"] == case.expected_document_ids[0]) == "tr"
                for case in cases
            ),
        },
    }
    return documents_payload, dataset, manifest


def write_corpus(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    documents, dataset, manifest = build_corpus()
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads = {
        "documents.json": documents,
        "dataset.json": dataset.model_dump(mode="json"),
        "manifest.json": manifest,
    }
    for filename, payload in payloads.items():
        (output_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return manifest


if __name__ == "__main__":
    print(json.dumps(write_corpus(), indent=2, sort_keys=True))
