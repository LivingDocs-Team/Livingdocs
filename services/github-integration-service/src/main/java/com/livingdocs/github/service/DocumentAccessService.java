package com.livingdocs.github.service;

import org.springframework.stereotype.Service;

@Service
public class DocumentAccessService {
    public boolean canReadDocument(String callerUserId, String docId) {
        // Tạm thời return true để pass compile. Hãy thay bằng logic thực tế của bạn.
        return true; 
    }
}