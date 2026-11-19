package shop;

import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/orders")
public class OrderController {

    /** Count orders of a customer. */
    @GetMapping("/{customerId}/count")
    public int countOrders(@PathVariable String customerId) {
        return 0;
    }

    @PostMapping
    public String createOrder(@RequestBody String body) {
        return "created";
    }
}
