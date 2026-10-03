"""Generate a fictional, directionally mirrored cross-language diagnostic set."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.evaluation.models import EvaluationCase, EvaluationDataset
from app.services.evaluation.synthetic_corpus import corpus_fingerprint


CORPUS_VERSION = "cross-language-mirror-v1"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "cross-language-mirror-v1"

# Each paired fact has one English and one Turkish source, plus semantically
# equivalent query intents in both languages. Keep the set separate from the
# canonical Compact Multilingual corpus.
MIRRORED_FACTS: tuple[dict[str, Any], ...] = (
    {
        "id": "annual-leave-carryover", "category": "hr",
        "en_title": "Annual leave carry-over", "tr_title": "İzin devri",
        "en_text": "Unused annual leave may be carried into the next leave year for up to 6 days.",
        "tr_text": "Kullanılmayan yıllık izin sonraki izin yılına en fazla 6 gün devredilebilir.",
        "en_question": "How many unused annual leave days may be carried into the next leave year?",
        "tr_question": "Kullanılmayan yıllık izin sonraki izin yılına en fazla kaç gün devredilebilir?",
        "en_fact": "6 days", "tr_fact": "6 gün",
    },
    {
        "id": "parental-leave-duration", "category": "hr",
        "en_title": "Parental leave duration", "tr_title": "Ebeveyn izni süresi",
        "en_text": "Eligible employees receive 18 weeks of parental leave.",
        "tr_text": "Uygun çalışanlara 18 hafta ebeveyn izni verilir.",
        "en_question": "How long is the parental leave entitlement?",
        "tr_question": "Ebeveyn izni hakkı ne kadar sürer?",
        "en_fact": "18 weeks", "tr_fact": "18 hafta",
    },
    {
        "id": "medical-note-threshold", "category": "hr",
        "en_title": "Medical note threshold", "tr_title": "Sağlık raporu eşiği",
        "en_text": "A medical note is required after 2 consecutive workdays of illness.",
        "tr_text": "Hastalık nedeniyle art arda 2 iş günü devamsızlıktan sonra sağlık raporu gerekir.",
        "en_question": "After how many consecutive workdays is a medical note required?",
        "tr_question": "Kaç iş günü üst üste devamsızlıktan sonra sağlık raporu gerekir?",
        "en_fact": "2 consecutive workdays", "tr_fact": "2 iş günü",
    },
    {
        "id": "api-token-lifetime", "category": "security",
        "en_title": "Personal API token lifetime", "tr_title": "Kişisel API belirtecinin ömrü",
        "en_text": "A personal API access token remains valid for 90 days after issuance.",
        "tr_text": "Kişisel API erişim belirteci oluşturulduktan sonra 90 gün geçerlidir.",
        "en_question": "How long does a personal API access token remain valid?",
        "tr_question": "Kişisel API erişim belirteci ne kadar süre geçerli kalır?",
        "en_fact": "90 days", "tr_fact": "90 gün",
    },
    {
        "id": "browser-session-timeout", "category": "security",
        "en_title": "Inactive browser session", "tr_title": "Etkin olmayan tarayıcı oturumu",
        "en_text": "An inactive browser session expires after 30 minutes.",
        "tr_text": "Etkin olmayan tarayıcı oturumu 30 dakika sonra sona erer.",
        "en_question": "When does an inactive browser session expire?",
        "tr_question": "Etkin olmayan tarayıcı oturumu ne zaman sona erer?",
        "en_fact": "30 minutes", "tr_fact": "30 dakika",
    },
    {
        "id": "mfa-recheck-interval", "category": "security",
        "en_title": "Managed-device MFA interval", "tr_title": "Yönetilen cihaz MFA aralığı",
        "en_text": "Managed devices must repeat multi-factor authentication every 12 hours.",
        "tr_text": "Yönetilen cihazlarda çok faktörlü doğrulama her 12 saatte bir yinelenmelidir.",
        "en_question": "How often must a managed device repeat multi-factor authentication?",
        "tr_question": "Yönetilen cihazda çok faktörlü doğrulama ne sıklıkla yinelenmelidir?",
        "en_fact": "12 hours", "tr_fact": "12 saat",
    },
    {
        "id": "account-lockout-threshold", "category": "security",
        "en_title": "Account lockout threshold", "tr_title": "Hesap kilidi eşiği",
        "en_text": "An account is locked after 5 consecutive failed sign-in attempts.",
        "tr_text": "Bir hesap art arda 5 başarısız giriş denemesinden sonra kilitlenir.",
        "en_question": "How many consecutive failed sign-ins lock an account?",
        "tr_question": "Bir hesabın kilitlenmesi için art arda kaç başarısız giriş gerekir?",
        "en_fact": "5 failed attempts", "tr_fact": "5 başarısız deneme",
    },
    {
        "id": "personnel-file-retention", "category": "operations",
        "en_title": "Personnel-file retention", "tr_title": "Personel dosyası saklama süresi",
        "en_text": "Personnel files are retained for 7 years after an employee leaves.",
        "tr_text": "Personel dosyaları çalışan ayrıldıktan sonra 7 yıl saklanır.",
        "en_question": "How long are personnel files retained after departure?",
        "tr_question": "Personel dosyaları ayrılıktan sonra ne kadar süre saklanır?",
        "en_fact": "7 years", "tr_fact": "7 yıl",
    },
    {
        "id": "audit-log-retention", "category": "security",
        "en_title": "Audit-log search window", "tr_title": "Denetim kaydı arama süresi",
        "en_text": "Security audit events remain searchable for 400 days after creation.",
        "tr_text": "Güvenlik denetim olayları oluşturulduktan sonra 400 gün aranabilir kalır.",
        "en_question": "For how many days do security audit events remain searchable?",
        "tr_question": "Güvenlik denetim olayları kaç gün boyunca aranabilir kalır?",
        "en_fact": "400 days", "tr_fact": "400 gün",
    },
    {
        "id": "backup-snapshot-retention", "category": "operations",
        "en_title": "Backup snapshot retention", "tr_title": "Yedek anlık görüntüsü saklama süresi",
        "en_text": "Backup snapshots are retained for 45 days from their creation date.",
        "tr_text": "Yedek anlık görüntüleri oluşturulma tarihinden itibaren 45 gün saklanır.",
        "en_question": "How long are backup snapshots retained?",
        "tr_question": "Yedek anlık görüntüleri ne kadar süre saklanır?",
        "en_fact": "45 days", "tr_fact": "45 gün",
    },
    {
        "id": "restore-test-interval", "category": "operations",
        "en_title": "Recovery restore-test interval", "tr_title": "Kurtarma testi aralığı",
        "en_text": "The operations team performs a recovery restore test every 90 days.",
        "tr_text": "Operasyon ekibi her 90 günde bir kurtarma geri yükleme testi yapar.",
        "en_question": "How often is a recovery restore test performed?",
        "tr_question": "Kurtarma geri yükleme testi ne sıklıkla yapılır?",
        "en_fact": "90 days", "tr_fact": "90 gün",
    },
    {
        "id": "purchase-approval-threshold", "category": "policy",
        "en_title": "Purchase approval threshold", "tr_title": "Satın alma onay eşiği",
        "en_text": "A purchase above $2,500 requires department-manager approval before ordering.",
        "tr_text": "2.500 ABD dolarını aşan bir satın alma siparişten önce bölüm yöneticisi onayı gerektirir.",
        "en_question": "Above what amount does a purchase require manager approval?",
        "tr_question": "Bir satın alma hangi tutarın üzerinde yönetici onayı gerektirir?",
        "en_fact": "$2,500", "tr_fact": "2.500 ABD doları",
    },
    {
        "id": "travel-receipt-deadline", "category": "policy",
        "en_title": "Travel receipt deadline", "tr_title": "Seyahat fişi teslim süresi",
        "en_text": "Travel receipts must be submitted within 10 business days after returning.",
        "tr_text": "Seyahat fişleri dönüşten sonraki 10 iş günü içinde teslim edilmelidir.",
        "en_question": "What is the deadline for submitting travel receipts after return?",
        "tr_question": "Seyahat fişleri dönüşten sonra en geç ne zaman teslim edilmelidir?",
        "en_fact": "10 business days", "tr_fact": "10 iş günü",
    },
    {
        "id": "daily-meal-allowance", "category": "policy",
        "en_title": "Daily meal allowance", "tr_title": "Günlük yemek ödeneği",
        "en_text": "The daily meal allowance on approved international travel is 45 euros.",
        "tr_text": "Onaylı uluslararası seyahatlerde günlük yemek ödeneği 45 avrodur.",
        "en_question": "What is the daily meal allowance for approved international travel?",
        "tr_question": "Onaylı uluslararası seyahatte günlük yemek ödeneği ne kadardır?",
        "en_fact": "45 euros", "tr_fact": "45 avro",
    },
    {
        "id": "hotel-reimbursement-cap", "category": "policy",
        "en_title": "Hotel nightly reimbursement cap", "tr_title": "Otel gecelik geri ödeme sınırı",
        "en_text": "Hotel reimbursement is capped at 160 euros per night.",
        "tr_text": "Otel masrafı geri ödemesi gecelik 160 avro ile sınırlıdır.",
        "en_question": "What is the maximum hotel reimbursement per night?",
        "tr_question": "Otel masrafı için gecelik en fazla ne kadar geri ödeme yapılır?",
        "en_fact": "160 euros per night", "tr_fact": "gecelik 160 avro",
    },
    {
        "id": "supplier-review-period", "category": "security",
        "en_title": "Supplier security-review period", "tr_title": "Tedarikçi güvenlik inceleme aralığı",
        "en_text": "An active supplier receives a security review once every 12 months.",
        "tr_text": "Etkin bir tedarikçi her 12 ayda bir güvenlik incelemesinden geçirilir.",
        "en_question": "How often does an active supplier receive a security review?",
        "tr_question": "Etkin bir tedarikçi ne sıklıkla güvenlik incelemesinden geçirilir?",
        "en_fact": "12 months", "tr_fact": "12 ay",
    },
    {
        "id": "invoice-payment-term", "category": "policy",
        "en_title": "Approved invoice payment term", "tr_title": "Onaylı fatura ödeme vadesi",
        "en_text": "A complete approved supplier invoice is paid within 30 days of registration.",
        "tr_text": "Eksiksiz ve onaylı bir tedarikçi faturası kayıttan sonra 30 gün içinde ödenir.",
        "en_question": "Within how many days is an approved supplier invoice paid?",
        "tr_question": "Onaylı bir tedarikçi faturası kaç gün içinde ödenir?",
        "en_fact": "30 days", "tr_fact": "30 gün",
    },
    {
        "id": "api-page-size", "category": "technical",
        "en_title": "API page-size limit", "tr_title": "API sayfa boyutu sınırı",
        "en_text": "A list API endpoint returns at most 100 records on one page.",
        "tr_text": "Bir liste API uç noktası tek sayfada en fazla 100 kayıt döndürür.",
        "en_question": "What is the maximum number of records in one API page?",
        "tr_question": "Bir API sayfasında en fazla kaç kayıt döner?",
        "en_fact": "100 records", "tr_fact": "100 kayıt",
    },
    {
        "id": "rate-limit-retries", "category": "technical",
        "en_title": "Rate-limit retry budget", "tr_title": "Hız sınırı yeniden deneme hakkı",
        "en_text": "After an HTTP 429 response, a client may retry at most 3 times.",
        "tr_text": "HTTP 429 yanıtından sonra istemci en fazla 3 kez yeniden deneyebilir.",
        "en_question": "How many retries are allowed after an HTTP 429 response?",
        "tr_question": "HTTP 429 yanıtından sonra kaç yeniden denemeye izin verilir?",
        "en_fact": "3 retries", "tr_fact": "3 kez",
    },
    {
        "id": "critical-patch-deadline", "category": "security",
        "en_title": "Critical security-patch deadline", "tr_title": "Kritik güvenlik yaması süresi",
        "en_text": "A validated critical security patch must be deployed within 72 hours.",
        "tr_text": "Doğrulanmış kritik bir güvenlik yaması 72 saat içinde dağıtılmalıdır.",
        "en_question": "Within what period must a validated critical patch be deployed?",
        "tr_question": "Doğrulanmış kritik bir yama ne kadar süre içinde dağıtılmalıdır?",
        "en_fact": "72 hours", "tr_fact": "72 saat",
    },
)


def build_corpus() -> tuple[dict[str, Any], EvaluationDataset, dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    cases: list[EvaluationCase] = []

    for pair_number, fact in enumerate(MIRRORED_FACTS, start=1):
        english_id = pair_number * 2 - 1
        turkish_id = pair_number * 2
        stem = fact["id"]
        documents.extend((
            {
                "document_id": english_id,
                "filename": f"mirror-{pair_number:02d}-en.md",
                "language": "en",
                "knowledge_base_ids": [1],
                "text": f"{fact['en_title']}. {fact['en_text']}",
            },
            {
                "document_id": turkish_id,
                "filename": f"mirror-{pair_number:02d}-tr.md",
                "language": "tr",
                "knowledge_base_ids": [1],
                "text": f"{fact['tr_title']}. {fact['tr_text']}",
            },
        ))
        cases.extend((
            EvaluationCase(
                id=f"{stem}-tr-query-en-source",
                category=fact["category"],
                question=fact["tr_question"],
                knowledge_base_ids=[1],
                language="tr",
                scenario_id=f"mirror-pair-{pair_number:02d}",
                expected_document_ids=[english_id],
                expected_facts=[fact["en_fact"]],
                confusable_document_ids=[turkish_id],
                top_k=3,
            ),
            EvaluationCase(
                id=f"{stem}-en-query-tr-source",
                category=fact["category"],
                question=fact["en_question"],
                knowledge_base_ids=[1],
                language="en",
                scenario_id=f"mirror-pair-{pair_number:02d}",
                expected_document_ids=[turkish_id],
                expected_facts=[fact["tr_fact"]],
                confusable_document_ids=[english_id],
                top_k=3,
            ),
        ))
    dataset = EvaluationDataset(version=1, name=CORPUS_VERSION, cases=cases)
    documents_payload = {"corpus_version": CORPUS_VERSION, "documents": documents}
    fingerprint = corpus_fingerprint(CORPUS_VERSION, dataset, documents)
    manifest = {
        "corpus_version": CORPUS_VERSION,
        "fingerprint_sha256": fingerprint,
        "document_count": len(documents),
        "case_count": len(cases),
        "mirrored_fact_pair_count": len(MIRRORED_FACTS),
        "directional_case_counts": {
            "tr_query_to_en_document": sum(case.language == "tr" for case in cases),
            "en_query_to_tr_document": sum(case.language == "en" for case in cases),
        },
        "all_facts_numeric_or_threshold_based": all(
            any(character.isdigit() for character in fact["en_fact"] + fact["tr_fact"])
            for fact in MIRRORED_FACTS
        ),
    }
    return documents_payload, dataset, manifest


def write_corpus(output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    documents, dataset, manifest = build_corpus()
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, payload in (
        ("documents.json", documents),
        ("dataset.json", dataset.model_dump(mode="json")),
        ("manifest.json", manifest),
    ):
        (output_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return manifest


if __name__ == "__main__":
    print(json.dumps(write_corpus(), indent=2, sort_keys=True))
