
import org.jetbrains.kotlin.gradle.tasks.KotlinCompile
import com.google.protobuf.gradle.*
import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    kotlin("jvm") version "2.2.21"
    application
    id("java")
    id("idea")
    id("com.google.protobuf") version "0.9.5"
    id("com.github.johnrengelman.shadow") version "8.1.1"
}

group = "io.opentelemetry"
version = "1.0"


val grpcVersion = "1.76.0"
val protobufVersion = "4.33.1"

// CVE-2026-42577: grpc-netty 1.76.0 pulls transitive Netty modules in the
// 4.2.x line where the epoll transport fails to close half-closed TCP
// connections (100% CPU busy-loop). Fixed in 4.2.13.Final.
// CVE-2026-44249: netty-handler <4.2.15.Final mis-masks IPv6 subnet rules
// in IpSubnetFilterRule.compareTo(), allowing valid public IPs to bypass
// restrictions. Fixed in 4.2.15.Final.
// Force all io.netty artifacts to 4.2.15.Final to cover both.
//
// CVE-2026-45292: opentelemetry-java <1.62.0 baggage propagation DoS.
// Transitive deps (openfeature-flagd provider, grpc bundles) still declare
// older opentelemetry-api versions (e.g. 1.41.0). Force every io.opentelemetry
// artifact to 1.62.0 so FOSSA no longer sees the vulnerable declared version.
configurations.all {
    resolutionStrategy.eachDependency {
        if (requested.group == "io.netty") {
            useVersion("4.2.15.Final")
        }
        if (requested.group == "io.opentelemetry") {
            useVersion("1.62.0")
        }
    }
}

repositories {
    mavenCentral()
    gradlePluginPortal()
}



dependencies {
    implementation("com.google.protobuf:protobuf-java:${protobufVersion}")
    implementation("com.google.protobuf:protobuf-java-util:${protobufVersion}")
    testImplementation(kotlin("test"))
    implementation(kotlin("script-runtime"))
    implementation("org.apache.kafka:kafka-clients:4.1.1")
    implementation("com.google.api.grpc:proto-google-common-protos:2.63.2")
    implementation("io.grpc:grpc-protobuf:${grpcVersion}")
    implementation("io.grpc:grpc-stub:${grpcVersion}")
    implementation("io.grpc:grpc-netty:${grpcVersion}")
    implementation("io.grpc:grpc-services:${grpcVersion}")
    // CVE-2026-45292: opentelemetry-java <1.62.0 baggage propagation is
    // vulnerable to unbounded CPU/memory when parsing oversized baggage.
    implementation("io.opentelemetry:opentelemetry-api:1.62.0")
    implementation("io.opentelemetry:opentelemetry-sdk:1.62.0")
    implementation("org.apache.logging.log4j:log4j-core:2.25.2")
    implementation("org.slf4j:slf4j-api:2.0.17")
    implementation("org.apache.logging.log4j:log4j-slf4j2-impl:2.25.2")
    implementation("com.google.protobuf:protobuf-kotlin:${protobufVersion}")
    implementation("dev.openfeature:sdk:1.18.2")
    implementation("dev.openfeature.contrib.providers:flagd:0.11.17")
    implementation("com.microsoft.sqlserver:mssql-jdbc:12.8.1.jre11")
    implementation("com.zaxxer:HikariCP:5.1.0")

    if (JavaVersion.current().isJava9Compatible) {
        // Workaround for @javax.annotation.Generated
        // see: https://github.com/grpc/grpc-java/issues/3633
        implementation("javax.annotation:javax.annotation-api:1.3.2")
    }
}

tasks {
    shadowJar {
        mergeServiceFiles()
    }
}

tasks.test {
    useJUnitPlatform()
}

kotlin {
  compilerOptions {
    jvmTarget.set(JvmTarget.JVM_17)
  }
}

protobuf {
    protoc {
        artifact = "com.google.protobuf:protoc:${protobufVersion}"
    }
    plugins {

        id("grpc") {
            artifact = "io.grpc:protoc-gen-grpc-java:${grpcVersion}"
        }
    }
    generateProtoTasks {
        ofSourceSet("main").forEach {
            it.plugins {
                // Apply the "grpc" plugin whose spec is defined above, without
                // options. Note the braces cannot be omitted, otherwise the
                // plugin will not be added. This is because of the implicit way
                // NamedDomainObjectContainer binds the methods.
                id("grpc") { }
            }
        }
    }
}

application {
    mainClass.set("frauddetection.MainKt")
}

tasks.jar {
    manifest.attributes["Main-Class"] = "frauddetection.MainKt"
}
