class GroundingEvidence(BaseModel):
    evidence_id: str = Field(..., description="ID bằng chứng (VD: E1, C1, D1)")
    file_path: str = Field(..., description="Đường dẫn tương đối của file code")
    start_line: Optional[int] = Field(None, ge=1, description="Dòng bắt đầu")
    end_line: Optional[int] = Field(None, ge=1, description="Dòng kết thúc")
    code_snippet: Optional[str] = Field(None, description="Trích đoạn code thực tế")
    commit_hash: str = Field(default="head", description="Commit hash của repo")


class EvidenceCollector:
    """LD-107: Collect Grounding Evidence từ Job Report."""

    @staticmethod
    def collect_from_job(job_id: str) -> List[GroundingEvidence]:
        report = jobs.get_report(job_id)
        if not report:
            return []

        evidence_list: List[GroundingEvidence] = []
        for file_rep in report.files:
            for entity in file_rep.entities:
                for ev in entity.evidence:
                    evidence_list.append(
                        GroundingEvidence(
                            evidence_id=ev.id,
                            file_path=ev.path,
                            start_line=ev.line_start,
                            end_line=ev.line_end,
                            code_snippet=ev.excerpt,
                            commit_hash="head",
                        )
                    )
        return evidence_list


class EvidenceDisplayService:
    """LD-108: Display Generation Evidence."""

    @staticmethod
    def get_document_evidence(document_id: str) -> List[GroundingEvidence]:
        job = jobs.get(document_id)
        if not job:
            raise HTTPException(status_code=404, detail="Document not found")
        return EvidenceCollector.collect_from_job(document_id)
