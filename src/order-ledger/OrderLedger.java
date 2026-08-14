// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
//
// order-ledger — minimal Java support service for accounting.
//
// Accounting fires a fire-and-forget POST /validate/{orderId} for every Kafka
// order it consumes (ORDER_VALIDATION_ADDR env). This service looks that order
// up in the accounting."order" table and returns whether it exists.
//
// Instrumented by the Splunk OpenTelemetry Java agent (added via JAVA_TOOL_OPTIONS
// in the k8s manifest). With OTEL_INSTRUMENTATION_SPLUNK_JDBC_ENABLED=true the
// DB lookup is correlated with the APM trace (DB Query Performance <-> APM), and
// the agent creates a server span from accounting's traceparent so the lookup
// nests under the order's trace.

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class OrderLedger {
    static String url, user, pass;

    public static void main(String[] args) throws Exception {
        url  = env("PG_URL",  "jdbc:postgresql://postgresql:5432/astroshop");
        user = env("PG_USER", "otelu");
        pass = env("PG_PASS", "otelp");
        int port = Integer.parseInt(env("PORT", "8080"));

        HttpServer s = HttpServer.create(new InetSocketAddress(port), 0);
        s.createContext("/validate", OrderLedger::handleValidate);
        s.createContext("/health", ex -> respond(ex, 200, "{\"ok\":true}"));
        s.setExecutor(null);
        System.out.println("order-ledger listening on :" + port + " -> " + url);
        s.start();
    }

    // POST /validate/{orderId} — look the order up in accounting."order".
    static void handleValidate(HttpExchange ex) throws java.io.IOException {
        String path = ex.getRequestURI().getPath();
        String prefix = "/validate/";
        String orderId = path.length() > prefix.length() ? path.substring(prefix.length()) : "";
        ex.getRequestBody().readAllBytes(); // accounting POSTs a JSON body; not needed here

        boolean found = false;
        String err = null;
        if (!orderId.isEmpty()) {
            String sql = "SELECT order_id FROM accounting.\"order\" WHERE order_id = ?";
            try (Connection c = DriverManager.getConnection(url, user, pass);
                 PreparedStatement ps = c.prepareStatement(sql)) {
                ps.setString(1, orderId);
                try (ResultSet rs = ps.executeQuery()) {
                    found = rs.next();
                }
            } catch (Exception e) {
                err = e.getMessage();
            }
        }

        int code = (err != null) ? 500 : 200;
        String body = (err != null)
            ? "{\"orderId\":\"" + esc(orderId) + "\",\"error\":\"" + esc(err) + "\"}"
            : "{\"orderId\":\"" + esc(orderId) + "\",\"found\":" + found + "}";
        System.out.println("validate order=" + orderId + " found=" + found + (err != null ? " err=" + err : ""));
        respond(ex, code, body);
    }

    static void respond(HttpExchange ex, int code, String body) throws java.io.IOException {
        byte[] b = body.getBytes();
        ex.getResponseHeaders().set("Content-Type", "application/json");
        ex.sendResponseHeaders(code, b.length);
        try (OutputStream os = ex.getResponseBody()) { os.write(b); }
    }

    static String esc(String s) {
        return s == null ? "" : s.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    static String env(String k, String d) {
        String v = System.getenv(k);
        return (v == null || v.isEmpty()) ? d : v;
    }
}
