package com.appd.e2e;

import org.eclipse.jetty.server.Server;
import org.eclipse.jetty.servlet.ServletContextHandler;
import org.eclipse.jetty.servlet.ServletHolder;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.*;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.net.HttpURLConnection;
import java.net.URL;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;

/**
 * Team Portal — a Jetty servlet-based collaboration application with
 * document conversion, link previews, user search, authentication,
 * and session management.
 *
 * Runs on embedded Jetty 9.4 with an H2 in-memory database.
 * Configurable port via -Dserver.port (default 8080).
 *
 * NOTE: This application intentionally uses vulnerable library versions
 * for security agent e2e testing.  Each endpoint exercises a specific
 * vulnerability class (RCE, SSRF, SQLi, Log4Shell, deserialization)
 * that the agent should detect and classify as EXPLOITED.
 */
public class JavaSecureAppTestApp {

    // --- Health check ---
    public static class HealthServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
            resp.setStatus(200);
            resp.getWriter().write("OK");
        }
    }

    // --- Document format conversion (exercises Struts2 CVE-2017-5638) ---
    // Internally routes through JakartaMultiPartRequest.buildErrorMessage()
    // which triggers ProcessBuilder.start().  The agent hooks ProcessBuilder,
    // sees buildErrorMessage on the stack, matches CVE-2017-5638 -> EXPLOITED.
    public static class DocumentConvertServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
            String result;
            try {
                VulnMultiPartRequest vuln = new VulnMultiPartRequest();
                vuln.triggerRce();
                result = "{\"status\": \"converted\", \"format\": \"pdf\"}";
            } catch (SecurityException se) {
                result = "{\"error\": \"" + se.getMessage() + "\"}";
            } catch (Exception e) {
                // NPE is expected — parent's buildErrorMessage uses uninitialized Struts
                // locale.  ProcessBuilder.start() already fired before the NPE.
                result = "{\"status\": \"converted\", \"format\": \"pdf\"}";
            }
            resp.setStatus(200);
            resp.setContentType("application/json");
            resp.getWriter().write(result);
        }
    }

    /**
     * Subclass of JakartaMultiPartRequest that does NOT override buildErrorMessage.
     * We pass a custom Throwable whose getMessage() executes ProcessBuilder, so the
     * parent's JakartaMultiPartRequest.buildErrorMessage appears on the stack when
     * ProcessBuilder.start() fires — matching the CVE-2017-5638 vuln_method feed.
     */
    public static class VulnMultiPartRequest
            extends org.apache.struts2.dispatcher.multipart.JakartaMultiPartRequest {

        public void triggerRce() {
            Throwable cause = new RceThrowable();
            buildErrorMessage(cause, new Object[0]);
        }
    }

    public static class RceThrowable extends RuntimeException {
        @Override
        public String getMessage() {
            try {
                ProcessBuilder pb = new ProcessBuilder("/bin/echo", "convert-document");
                pb.redirectErrorStream(true);
                Process proc = pb.start();
                proc.waitFor();
            } catch (Exception ex) {
                // ignored
            }
            return "multipart parse error during document conversion";
        }
    }

    // --- Link metadata preview (exercises SSRF to cloud metadata) ---
    // Fetches a URL to generate a link preview.  The hardcoded URL targets
    // the AWS metadata endpoint; the agent detects the socket connect to
    // 169.254.169.254 and classifies it as SSRF -> EXPLOITED.
    public static class LinkPreviewServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
            String result;
            try {
                URL url = new URL("http://169.254.169.254/latest/meta-data/");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(2000);
                conn.setReadTimeout(2000);
                conn.getResponseCode();
                conn.disconnect();
                result = "{\"status\": \"ok\", \"title\": \"Cloud Metadata\", \"url\": \"http://169.254.169.254/\"}";
            } catch (SecurityException se) {
                result = "{\"error\": \"" + se.getMessage() + "\"}";
            } catch (Exception e) {
                result = "{\"error\": \"" + e.getMessage() + "\"}";
            }
            resp.setStatus(200);
            resp.setContentType("application/json");
            resp.getWriter().write(result);
        }
    }

    // --- User directory search (exercises SQL injection) ---
    // Concatenates input into a SQL query without parameterization.
    // The agent detects contains_or_true and contains_comment signals -> EXPLOITED.
    // NOTE: DB setup is done once at startup to avoid dedup issues.
    public static class UserSearchServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
            String result;
            try {
                Class.forName("org.h2.Driver");
                Connection conn = DriverManager.getConnection(
                    "jdbc:h2:mem:testdb;DB_CLOSE_DELAY=-1", "sa", "");
                Statement stmt = conn.createStatement();
                String searchTerm = "' OR 1=1 --";
                String sql = "SELECT * FROM users WHERE name = '" + searchTerm + "'";
                ResultSet rs = stmt.executeQuery(sql);
                int count = 0;
                while (rs.next()) count++;
                rs.close();
                stmt.close();
                conn.close();
                result = "{\"count\": " + count + ", \"results\": []}";
            } catch (SecurityException se) {
                result = "{\"error\": \"" + se.getMessage() + "\"}";
            } catch (Exception e) {
                result = "{\"error\": \"" + e.getClass().getSimpleName() + ": " + e.getMessage() + "\"}";
            }
            resp.setStatus(200);
            resp.setContentType("application/json");
            resp.setCharacterEncoding("UTF-8");
            resp.getWriter().write(result);
        }
    }

    // --- User authentication (exercises Log4j CVE-2021-44228) ---
    // Logs a username via Log4j 2.12.1 which evaluates JNDI lookup strings.
    // The agent detects the JNDI socket resolve with JndiLookup.lookup on
    // the stack -> EXPLOITED.
    public static class LoginServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
            String result;
            try {
                Class<?> logManagerClass = Class.forName("org.apache.logging.log4j.LogManager");
                Method getLoggerMethod = logManagerClass.getMethod("getLogger", String.class);
                Object logger = getLoggerMethod.invoke(null, "TeamPortal");
                Method errorMethod = logger.getClass().getMethod("error", String.class);
                errorMethod.invoke(logger, "${jndi:ldap://127.0.0.1:1389/log4j-test}");
                result = "{\"status\": \"failed\", \"message\": \"Invalid credentials\"}";
            } catch (SecurityException se) {
                result = "{\"error\": \"" + se.getMessage() + "\"}";
            } catch (Exception e) {
                result = "{\"status\": \"failed\", \"message\": \"Authentication error\"}";
            }
            resp.setStatus(200);
            resp.setContentType("application/json");
            resp.getWriter().write(result);
        }
    }

    // --- Session import (exercises deserialization CVE-2020-1714) ---
    // Deserializes a session token via Keycloak's KerberosSerializationUtils,
    // which internally calls plain ObjectInputStream.readObject().  The agent
    // hooks OIS.resolveClass() and sees KerberosSerializationUtils.deserialize
    // on the stack -> matches CVE-2020-1714 -> EXPLOITED.
    public static class SessionImportServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
            String result;
            try {
                byte[] serializedBytes = createSerializedDiskFileItem();
                String base64Payload = org.keycloak.common.util.Base64.encodeBytes(serializedBytes);
                org.keycloak.common.util.KerberosSerializationUtils.deserializeCredential(base64Payload);
                result = "{\"status\": \"imported\"}";
            } catch (SecurityException se) {
                result = "{\"error\": \"" + se.getMessage() + "\"}";
            } catch (ClassCastException cce) {
                // Expected: deserialized object is not a GSSCredential.
                // Agent hook already fired during resolveClass().
                result = "{\"status\": \"imported\", \"session\": \"restored\"}";
            } catch (Exception e) {
                Throwable cause = e;
                while (cause.getCause() != null) cause = cause.getCause();
                result = "{\"status\": \"imported\", \"session\": \"restored\"}";
            }
            resp.setStatus(200);
            resp.setContentType("application/json");
            resp.getWriter().write(result);
        }

        byte[] createSerializedDiskFileItem() throws Exception {
            Class<?> dfiClass = Class.forName(
                "org.apache.commons.fileupload.disk.DiskFileItem");
            Constructor<?> ctor = dfiClass.getConstructor(
                String.class, String.class, boolean.class,
                String.class, int.class, java.io.File.class);
            Object dfi = ctor.newInstance(
                "file", "application/octet-stream", false,
                "session.dat", 10240, new java.io.File(System.getProperty("java.io.tmpdir")));
            Method getOS = dfiClass.getMethod("getOutputStream");
            OutputStream os = (OutputStream) getOS.invoke(dfi);
            os.write("session-data-for-restore".getBytes());
            os.close();
            ByteArrayOutputStream baos = new ByteArrayOutputStream();
            ObjectOutputStream oos = new ObjectOutputStream(baos);
            oos.writeObject(dfi);
            oos.close();
            return baos.toByteArray();
        }
    }

    // --- Shipping quote (calls the shipping service over HTTP) ---
    // Makes an outbound HTTP POST to shipping's /get-quote endpoint.
    // The Java agent auto-instruments HttpURLConnection, creating a child
    // span that links this service to shipping in the trace topology.
    // Skipped when SHIPPING_ADDR is not set (secureapp deployed standalone).
    public static class ShippingQuoteServlet extends HttpServlet {
        private static final String SHIPPING_ADDR = System.getenv("SHIPPING_ADDR");

        @Override
        protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
            String result = getShippingQuote();
            resp.setStatus(200);
            resp.setContentType("application/json");
            resp.getWriter().write(result);
        }

        static String getShippingQuote() {
            if (SHIPPING_ADDR == null || SHIPPING_ADDR.isEmpty()) {
                return "{\"status\": \"skipped\", \"reason\": \"SHIPPING_ADDR not set\"}";
            }
            try {
                String body = "{\"items\":[{\"productId\":\"OLJCESPC7Z\",\"quantity\":1}],"
                    + "\"address\":{\"streetAddress\":\"1600 Amphitheatre Parkway\","
                    + "\"city\":\"Mountain View\",\"state\":\"CA\","
                    + "\"country\":\"US\",\"zipCode\":\"94043\"}}";
                URL url = new URL(SHIPPING_ADDR + "/get-quote");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setConnectTimeout(3000);
                conn.setReadTimeout(3000);
                conn.setDoOutput(true);
                conn.getOutputStream().write(body.getBytes());
                int code = conn.getResponseCode();
                BufferedReader reader = new BufferedReader(
                    new InputStreamReader(conn.getInputStream()));
                StringBuilder sb = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) sb.append(line);
                reader.close();
                conn.disconnect();
                return "{\"status\": \"ok\", \"http_code\": " + code
                    + ", \"quote\": " + sb.toString() + "}";
            } catch (Exception e) {
                return "{\"status\": \"error\", \"message\": \""
                    + e.getClass().getSimpleName() + ": " + e.getMessage() + "\"}";
            }
        }
    }

    // --- Workspace sync (triggers all attack types in a single transaction) ---
    // A single HTTP request that exercises RCE, SSRF, SQLi, Log4Shell, and
    // deserialization in one web transaction so all events are grouped under
    // one attack summary with attackTypes = {RCE,SSRF,SQL,LOG4J,DESEREAL}.
    public static class WorkspaceSyncServlet extends HttpServlet {
        @Override
        protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
            StringBuilder log = new StringBuilder();

            // 1. RCE (Struts2 CVE-2017-5638)
            try {
                VulnMultiPartRequest vuln = new VulnMultiPartRequest();
                vuln.triggerRce();
                log.append("rce:ok ");
            } catch (Exception e) {
                log.append("rce:ok ");
            }

            // 2. SSRF (cloud metadata)
            try {
                URL url = new URL("http://169.254.169.254/latest/meta-data/");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(2000);
                conn.setReadTimeout(2000);
                conn.getResponseCode();
                conn.disconnect();
                log.append("ssrf:ok ");
            } catch (Exception e) {
                log.append("ssrf:ok ");
            }

            // 3. SQL injection
            try {
                Class.forName("org.h2.Driver");
                Connection conn = DriverManager.getConnection(
                    "jdbc:h2:mem:testdb;DB_CLOSE_DELAY=-1", "sa", "");
                Statement stmt = conn.createStatement();
                String sql = "SELECT * FROM users WHERE name = '' OR 1=1 --'";
                ResultSet rs = stmt.executeQuery(sql);
                rs.close();
                stmt.close();
                conn.close();
                log.append("sql:ok ");
            } catch (Exception e) {
                log.append("sql:ok ");
            }

            // 4. Log4Shell (CVE-2021-44228)
            try {
                Class<?> logManagerClass = Class.forName("org.apache.logging.log4j.LogManager");
                Method getLoggerMethod = logManagerClass.getMethod("getLogger", String.class);
                Object logger = getLoggerMethod.invoke(null, "TeamPortal");
                Method errorMethod = logger.getClass().getMethod("error", String.class);
                errorMethod.invoke(logger, "${jndi:ldap://127.0.0.1:1389/log4j-test}");
                log.append("log4j:ok ");
            } catch (Exception e) {
                log.append("log4j:ok ");
            }

            // 5. Deserialization (CVE-2020-1714)
            try {
                SessionImportServlet helper = new SessionImportServlet();
                byte[] serializedBytes = helper.createSerializedDiskFileItem();
                String base64Payload = org.keycloak.common.util.Base64.encodeBytes(serializedBytes);
                org.keycloak.common.util.KerberosSerializationUtils.deserializeCredential(base64Payload);
                log.append("deserial:ok ");
            } catch (Exception e) {
                log.append("deserial:ok ");
            }

            // 6. Shipping quote (outbound HTTP to shipping service)
            try {
                String quoteResult = ShippingQuoteServlet.getShippingQuote();
                log.append(quoteResult.contains("\"ok\"") ? "shipping:ok " : "shipping:skip ");
            } catch (Exception e) {
                log.append("shipping:err ");
            }

            resp.setStatus(200);
            resp.setContentType("application/json");
            resp.getWriter().write("{\"status\": \"synced\", \"steps\": \"" + log.toString().trim() + "\"}");
        }
    }

    public static void main(String[] args) throws Exception {
        int port = Integer.parseInt(System.getProperty("server.port", "8080"));

        Server server = new Server(port);
        ServletContextHandler context = new ServletContextHandler(ServletContextHandler.SESSIONS);
        context.setContextPath("/");
        server.setHandler(context);

        // Primary endpoints (realistic API paths)
        context.addServlet(new ServletHolder(new HealthServlet()), "/health");
        context.addServlet(new ServletHolder(new DocumentConvertServlet()), "/api/v1/documents/convert");
        context.addServlet(new ServletHolder(new LinkPreviewServlet()), "/api/v1/links/preview");
        context.addServlet(new ServletHolder(new UserSearchServlet()), "/api/v1/users/search");
        context.addServlet(new ServletHolder(new LoginServlet()), "/api/v1/auth/login");
        context.addServlet(new ServletHolder(new SessionImportServlet()), "/api/v1/sessions/import");
        context.addServlet(new ServletHolder(new WorkspaceSyncServlet()), "/api/v1/workspace/sync");
        context.addServlet(new ServletHolder(new ShippingQuoteServlet()), "/api/v1/shipping/estimate");

        // Legacy aliases for backward compatibility
        context.addServlet(new ServletHolder(new DocumentConvertServlet()), "/attack/rce-struts");
        context.addServlet(new ServletHolder(new LinkPreviewServlet()), "/attack/ssrf");
        context.addServlet(new ServletHolder(new UserSearchServlet()), "/attack/sqli");
        context.addServlet(new ServletHolder(new LoginServlet()), "/attack/log4j");
        context.addServlet(new ServletHolder(new SessionImportServlet()), "/attack/deserialization-cve");

        server.start();
        System.out.println("Team Portal started on port " + port);
        System.out.println("API endpoints:");
        System.out.println("  GET  /api/v1/documents/convert  - Document format conversion");
        System.out.println("  GET  /api/v1/links/preview      - Link metadata preview");
        System.out.println("  GET  /api/v1/users/search       - User directory search");
        System.out.println("  GET  /api/v1/auth/login         - User authentication");
        System.out.println("  GET  /api/v1/sessions/import    - Session restore");
        System.out.println("  GET  /api/v1/workspace/sync     - Workspace sync (all attacks in one)");
        System.out.println("  GET  /api/v1/shipping/estimate  - Shipping quote (calls shipping service)");
        System.out.println("  GET  /health                    - Health check");

        // Set up H2 in-memory DB (done once at startup, NOT per-request,
        // to avoid backend dedup merging CREATE/MERGE events with the
        // malicious SELECT and losing the SQL signals).
        try {
            Class.forName("org.h2.Driver");
            Connection dbConn = DriverManager.getConnection(
                "jdbc:h2:mem:testdb;DB_CLOSE_DELAY=-1", "sa", "");
            Statement dbStmt = dbConn.createStatement();
            dbStmt.execute("CREATE TABLE IF NOT EXISTS users (id INT, name VARCHAR(255), email VARCHAR(255), role VARCHAR(64))");
            dbStmt.execute("MERGE INTO users KEY(id) VALUES (1, 'admin', 'admin@teamportal.local', 'admin')");
            dbStmt.execute("MERGE INTO users KEY(id) VALUES (2, 'jdoe', 'jdoe@teamportal.local', 'user')");
            dbStmt.execute("MERGE INTO users KEY(id) VALUES (3, 'alice', 'alice@teamportal.local', 'user')");
            dbStmt.close();
            dbConn.close();
            System.out.println("Database initialized.");
        } catch (Exception e) {
            System.out.println("Database setup error: " + e.getMessage());
        }

        // Load classes from third-party JARs for VA scanner discovery
        System.out.println("\nLoading application libraries...");
        String[][] libs = {
            {"org.apache.logging.log4j.LogManager", "log4j"},
            {"org.apache.commons.lang3.StringUtils", "commons-lang3"},
            {"org.apache.commons.io.IOUtils", "commons-io"},
            {"com.google.common.collect.ImmutableList", "guava"},
            {"freemarker.template.Configuration", "freemarker"},
            {"ognl.Ognl", "ognl"},
            {"org.apache.commons.collections.functors.InvokerTransformer", "commons-collections"},
            {"org.apache.commons.fileupload.disk.DiskFileItem", "commons-fileupload"},
            {"com.fasterxml.jackson.databind.ObjectMapper", "jackson-databind"},
            {"org.apache.activemq.util.ClassLoadingAwareObjectInputStream", "activemq-client"},
            {"org.keycloak.common.util.KerberosSerializationUtils", "keycloak-common"},
        };
        for (String[] lib : libs) {
            try {
                Class.forName(lib[0]);
                System.out.println("  " + lib[1]);
            } catch (Exception e) {
                System.out.println("  " + lib[1] + ": " + e.getMessage());
            }
        }
        System.out.println("Ready.");

        server.join();
    }
}
