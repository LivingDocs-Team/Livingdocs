package com.acme.shop.web;

import java.util.List;
import org.springframework.web.bind.annotation.*;

/** REST API for orders. */
@RestController
@RequestMapping("/orders")
public class OrderApi {
    private final OrderService service;

    /** Create the controller. */
    public OrderApi(OrderService service) {
        this.service = service;
    }

    /**
     * Get one order.
     * @param id order id
     * @return the order
     */
    @GetMapping("/{id}")
    public Order get(@PathVariable Long id) {
        return service.find(id);
    }

    /** Find an order by its public code. */
    public Order get(String code) {
        return service.findByCode(code);
    }

    @PostMapping
    public Order create(@RequestBody Order order) {
        return service.save(order);
    }
}

/** Storage of orders. */
interface OrderService {
    Order find(Long id);
    Order findByCode(String code);
    Order save(Order order);
}

enum OrderStatus { NEW, PAID }
