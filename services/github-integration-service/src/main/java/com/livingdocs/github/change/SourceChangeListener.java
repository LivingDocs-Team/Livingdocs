package com.livingdocs.github.change;

import com.livingdocs.github.service.SourceChangeService;
import jakarta.annotation.PreDestroy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionalEventListener;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * LD-116: chạy phát hiện thay đổi ở nền, sau khi transaction lưu webhook đã commit,
 * để GitHub nhận phản hồi ngay (GitHub chỉ chờ webhook khoảng 10 giây).
 */
@Component
public class SourceChangeListener {

    private static final Logger log = LoggerFactory.getLogger(SourceChangeListener.class);

    private final SourceChangeService sourceChangeService;
    private final ExecutorService executor = Executors.newFixedThreadPool(2, task -> {
        Thread thread = new Thread(task, "source-change-detection");
        thread.setDaemon(true);
        return thread;
    });

    public SourceChangeListener(SourceChangeService sourceChangeService) {
        this.sourceChangeService = sourceChangeService;
    }

    @TransactionalEventListener
    public void onRequest(SourceChangeRequest request) {
        executor.execute(() -> {
            try {
                sourceChangeService.detect(request);
            } catch (RuntimeException e) {
                log.warn("Source change detection failed for {}: {}", request, e.getMessage());
            }
        });
    }

    @PreDestroy
    void shutdown() {
        executor.shutdown();
    }
}
