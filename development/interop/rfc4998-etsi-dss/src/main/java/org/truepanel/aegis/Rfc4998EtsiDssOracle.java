package org.truepanel.aegis;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;
import java.util.Base64;
import java.util.Collections;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import eu.europa.esig.dss.diagnostic.DiagnosticData;
import eu.europa.esig.dss.diagnostic.EvidenceRecordWrapper;
import eu.europa.esig.dss.diagnostic.TimestampWrapper;
import eu.europa.esig.dss.evidencerecord.asn1.validation.ASN1EvidenceRecordValidator;
import eu.europa.esig.dss.model.InMemoryDocument;
import eu.europa.esig.dss.spi.DSSUtils;
import eu.europa.esig.dss.spi.validation.CommonCertificateVerifier;
import eu.europa.esig.dss.spi.x509.CommonTrustedCertificateSource;
import eu.europa.esig.dss.validation.reports.Reports;

public final class Rfc4998EtsiDssOracle {
    private static final String ORACLE_VERSION = "6.5.1";

    private Rfc4998EtsiDssOracle() {
    }

    private static final class ValidationSnapshot {
        private final boolean structuralValid;
        private final boolean detachedDataFound;
        private final boolean detachedDataIntact;
        private final boolean timestampSignatureValid;
        private final boolean timestampImprintIntact;
        private final boolean trustAnchorReached;

        private ValidationSnapshot(
                boolean structuralValid,
                boolean detachedDataFound,
                boolean detachedDataIntact,
                boolean timestampSignatureValid,
                boolean timestampImprintIntact,
                boolean trustAnchorReached) {
            this.structuralValid = structuralValid;
            this.detachedDataFound = detachedDataFound;
            this.detachedDataIntact = detachedDataIntact;
            this.timestampSignatureValid = timestampSignatureValid;
            this.timestampImprintIntact = timestampImprintIntact;
            this.trustAnchorReached = trustAnchorReached;
        }

        private boolean passed() {
            return structuralValid
                    && detachedDataFound
                    && detachedDataIntact
                    && timestampSignatureValid
                    && timestampImprintIntact
                    && trustAnchorReached;
        }
    }

    private static String field(String json, String name) {
        Pattern pattern = Pattern.compile("\\\"" + Pattern.quote(name) + "\\\":\\\"([^\\\"]+)\\\"");
        Matcher matcher = pattern.matcher(json);
        if (!matcher.find()) {
            throw new IllegalArgumentException("missing fixture field: " + name);
        }
        return matcher.group(1);
    }

    private static byte[] decodedField(String json, String name) {
        return Base64.getDecoder().decode(field(json, name));
    }

    private static String hex(byte[] value) {
        StringBuilder result = new StringBuilder(value.length * 2);
        for (byte item : value) {
            result.append(String.format("%02x", item & 0xff));
        }
        return result.toString();
    }

    private static byte[] digest(String algorithm, byte[] value) throws Exception {
        return MessageDigest.getInstance(algorithm).digest(value);
    }

    private static ValidationSnapshot validate(byte[] record, byte[] data, byte[] trustedRoot) {
        CommonTrustedCertificateSource trust = new CommonTrustedCertificateSource();
        trust.addCertificate(DSSUtils.loadCertificate(trustedRoot));
        CommonCertificateVerifier certificateVerifier = new CommonCertificateVerifier();
        certificateVerifier.setTrustedCertSources(trust);

        ASN1EvidenceRecordValidator validator = new ASN1EvidenceRecordValidator(
                new InMemoryDocument(record, "aegis-rfc4998.ers"));
        validator.setCertificateVerifier(certificateVerifier);
        validator.setDetachedContents(Collections.singletonList(
                new InMemoryDocument(data, "aegis-detached-data.bin")));
        Reports reports = validator.validateDocument();
        DiagnosticData diagnostic = reports.getDiagnosticData();
        List<EvidenceRecordWrapper> records = diagnostic.getEvidenceRecords();
        if (records.size() != 1) {
            throw new IllegalStateException("expected one evidence record, got " + records.size());
        }
        EvidenceRecordWrapper evidenceRecord = records.get(0);
        List<TimestampWrapper> timestamps = evidenceRecord.getTimestampList();
        if (timestamps.size() != 1) {
            throw new IllegalStateException("expected one archive timestamp, got " + timestamps.size());
        }
        TimestampWrapper timestamp = timestamps.get(0);
        boolean trustReached = timestamp.getCertificateChain().stream().anyMatch(certificate -> certificate.isTrusted());
        return new ValidationSnapshot(
                evidenceRecord.isStructuralValidationValid(),
                timestamp.isMessageImprintDataFound(),
                timestamp.isMessageImprintDataIntact(),
                timestamp.isSignatureValid(),
                timestamp.isMessageImprintDataIntact(),
                trustReached);
    }

    private static void expectMalformed(byte[] value) {
        try {
            new ASN1EvidenceRecordValidator(new InMemoryDocument(value, "truncated.ers"));
        } catch (RuntimeException expected) {
            return;
        }
        throw new IllegalStateException("truncated record was accepted");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("usage: FIXTURE_JSON RECEIPT_JSON");
        }
        String fixture = Files.readString(Path.of(args[0]), StandardCharsets.UTF_8);
        byte[] record = decodedField(fixture, "evidence_record_der_base64");
        byte[] data = decodedField(fixture, "detached_data_base64");
        byte[] trustedRoot = decodedField(fixture, "trusted_root_pem_base64");
        byte[] wrongRoot = decodedField(fixture, "wrong_root_pem_base64");

        String recordSha256 = hex(digest("SHA-256", record));
        String dataSha512 = hex(digest("SHA-512", data));
        if (!recordSha256.equals(field(fixture, "evidence_record_sha256"))) {
            throw new IllegalStateException("fixture record hash mismatch");
        }
        if (!dataSha512.equals(field(fixture, "detached_data_sha512"))) {
            throw new IllegalStateException("fixture detached-data hash mismatch");
        }

        ValidationSnapshot accepted = validate(record, data, trustedRoot);
        if (!accepted.passed()) {
            throw new IllegalStateException("ETSI DSS did not accept the exact fixture");
        }
        byte[] wrongData = data.clone();
        wrongData[0] ^= 1;
        ValidationSnapshot wrongDataResult = validate(record, wrongData, trustedRoot);
        if (wrongDataResult.timestampImprintIntact || wrongDataResult.passed()) {
            throw new IllegalStateException("wrong detached data was accepted");
        }
        ValidationSnapshot wrongRootResult = validate(record, data, wrongRoot);
        if (wrongRootResult.trustAnchorReached || wrongRootResult.passed()) {
            throw new IllegalStateException("wrong trust anchor was accepted");
        }
        expectMalformed(Arrays.copyOf(record, record.length - 1));

        String receipt = "{"
                + "\"schema\":\"truepanel.aegis-rfc4998-etsi-dss-receipt/v1\","
                + "\"oracle\":\"European Commission ETSI DSS\","
                + "\"oracle_version\":\"" + ORACLE_VERSION + "\","
                + "\"fixture_sha256\":\"" + recordSha256 + "\","
                + "\"detached_data_sha512\":\"" + dataSha512 + "\","
                + "\"record_parsed\":true,"
                + "\"structural_validation_valid\":true,"
                + "\"detached_data_found\":true,"
                + "\"detached_data_intact\":true,"
                + "\"timestamp_signature_valid\":true,"
                + "\"timestamp_imprint_intact\":true,"
                + "\"trust_anchor_reached\":true,"
                + "\"wrong_data_rejected\":true,"
                + "\"truncated_record_rejected\":true,"
                + "\"wrong_trust_anchor_rejected\":true,"
                + "\"external_validations_completed\":2,"
                + "\"production_trusted\":false,"
                + "\"deployment_authority\":false,"
                + "\"hardware_authority\":false}"
                + System.lineSeparator();
        Path receiptPath = Path.of(args[1]);
        Files.createDirectories(receiptPath.toAbsolutePath().getParent());
        Files.writeString(receiptPath, receipt, StandardCharsets.UTF_8);
        System.out.print(receipt);
    }
}
