package org.truepanel.aegis;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.Security;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.Base64;
import java.util.Date;
import java.util.List;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.bouncycastle.asn1.cms.ContentInfo;
import org.bouncycastle.asn1.tsp.ArchiveTimeStamp;
import org.bouncycastle.asn1.tsp.ArchiveTimeStampChain;
import org.bouncycastle.asn1.tsp.ArchiveTimeStampSequence;
import org.bouncycastle.cert.X509CertificateHolder;
import org.bouncycastle.cert.jcajce.JcaX509CertificateConverter;
import org.bouncycastle.cms.CMSSignedData;
import org.bouncycastle.cms.jcajce.JcaSimpleSignerInfoVerifierBuilder;
import org.bouncycastle.jce.provider.BouncyCastleProvider;
import org.bouncycastle.operator.DigestCalculatorProvider;
import org.bouncycastle.operator.jcajce.JcaDigestCalculatorProviderBuilder;
import org.bouncycastle.tsp.TimeStampToken;
import org.bouncycastle.tsp.ers.ERSByteData;
import org.bouncycastle.tsp.ers.ERSEvidenceRecord;

public final class Rfc4998BouncyCastleOracle {
    private static final String ORACLE_VERSION = "1.86";

    private Rfc4998BouncyCastleOracle() {
    }

    @FunctionalInterface
    private interface CheckedOperation {
        void run() throws Exception;
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

    private static X509Certificate certificate(byte[] pem) throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        return (X509Certificate) factory.generateCertificate(new ByteArrayInputStream(pem));
    }

    private static Date timestampTime(ERSEvidenceRecord record) throws Exception {
        ArchiveTimeStampSequence sequence = record.toASN1Structure().getArchiveTimeStampSequence();
        ArchiveTimeStampChain[] chains = sequence.getArchiveTimeStampChains();
        ArchiveTimeStamp[] stamps = chains[0].getArchiveTimestamps();
        ContentInfo contentInfo = stamps[0].getTimeStamp();
        return new TimeStampToken(new CMSSignedData(contentInfo)).getTimeStampInfo().getGenTime();
    }

    private static void validateTrust(
            ERSEvidenceRecord record,
            X509Certificate trustedRoot,
            Date validationTime) throws Exception {
        X509CertificateHolder holder = record.getSigningCertificate();
        if (holder == null) {
            throw new IllegalStateException("timestamp signing certificate absent");
        }
        X509Certificate signer = new JcaX509CertificateConverter()
                .setProvider(BouncyCastleProvider.PROVIDER_NAME)
                .getCertificate(holder);
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        CertPath path = factory.generateCertPath(List.of(signer));
        PKIXParameters parameters = new PKIXParameters(Set.of(new TrustAnchor(trustedRoot, null)));
        parameters.setRevocationEnabled(false);
        parameters.setDate(validationTime);
        CertPathValidator.getInstance("PKIX").validate(path, parameters);
    }

    private static void validate(
            ERSEvidenceRecord record,
            byte[] detachedData,
            X509Certificate trustedRoot,
            Date timestampTime) throws Exception {
        record.validatePresent(new ERSByteData(detachedData), new Date());
        X509CertificateHolder signer = record.getSigningCertificate();
        record.validate(new JcaSimpleSignerInfoVerifierBuilder()
                .setProvider(BouncyCastleProvider.PROVIDER_NAME)
                .build(signer));
        validateTrust(record, trustedRoot, timestampTime);
    }

    private static void expectFailure(String name, CheckedOperation operation) throws Exception {
        try {
            operation.run();
        } catch (Exception expected) {
            return;
        }
        throw new IllegalStateException(name + " was accepted");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("usage: FIXTURE_JSON RECEIPT_JSON");
        }
        BouncyCastleProvider provider = new BouncyCastleProvider();
        Security.addProvider(provider);
        if (!ORACLE_VERSION.equals(provider.getVersionStr())) {
            throw new IllegalStateException("unexpected Bouncy Castle version: " + provider.getVersionStr());
        }

        String fixture = Files.readString(Path.of(args[0]), StandardCharsets.UTF_8);
        byte[] recordBytes = decodedField(fixture, "evidence_record_der_base64");
        byte[] detachedData = decodedField(fixture, "detached_data_base64");
        X509Certificate trustedRoot = certificate(decodedField(fixture, "trusted_root_pem_base64"));
        X509Certificate wrongRoot = certificate(decodedField(fixture, "wrong_root_pem_base64"));

        String recordSha256 = hex(digest("SHA-256", recordBytes));
        String detachedSha512 = hex(digest("SHA-512", detachedData));
        if (!recordSha256.equals(field(fixture, "evidence_record_sha256"))) {
            throw new IllegalStateException("fixture record hash mismatch");
        }
        if (!detachedSha512.equals(field(fixture, "detached_data_sha512"))) {
            throw new IllegalStateException("fixture detached-data hash mismatch");
        }

        DigestCalculatorProvider calculators = new JcaDigestCalculatorProviderBuilder()
                .setProvider(BouncyCastleProvider.PROVIDER_NAME)
                .build();
        ERSEvidenceRecord record = new ERSEvidenceRecord(recordBytes, calculators);
        Date generatedAt = timestampTime(record);
        byte[] primaryRoot = record.getPrimaryRootHash();
        if (!Arrays.equals(primaryRoot, digest("SHA-512", detachedData))) {
            throw new IllegalStateException("primary timestamp imprint mismatch");
        }
        if (!Arrays.equals(recordBytes, record.getEncoded())) {
            throw new IllegalStateException("record DER round-trip mismatch");
        }
        validate(record, detachedData, trustedRoot, generatedAt);

        byte[] wrongData = detachedData.clone();
        wrongData[0] ^= 1;
        expectFailure("wrong detached data", () ->
                record.validatePresent(new ERSByteData(wrongData), new Date()));
        byte[] truncated = Arrays.copyOf(recordBytes, recordBytes.length - 1);
        expectFailure("truncated record", () -> new ERSEvidenceRecord(truncated, calculators));
        expectFailure("wrong trust anchor", () ->
                validateTrust(record, wrongRoot, generatedAt));

        String receipt = "{"
                + "\"schema\":\"truepanel.aegis-rfc4998-bouncycastle-receipt/v1\","
                + "\"oracle\":\"Bouncy Castle\","
                + "\"oracle_version\":\"" + ORACLE_VERSION + "\","
                + "\"fixture_sha256\":\"" + recordSha256 + "\","
                + "\"detached_data_sha512\":\"" + detachedSha512 + "\","
                + "\"primary_imprint_sha512\":\"" + hex(primaryRoot) + "\","
                + "\"record_parsed\":true,"
                + "\"der_round_trip_exact\":true,"
                + "\"detached_data_present\":true,"
                + "\"timestamp_signature_valid\":true,"
                + "\"pkix_chain_valid_at_timestamp\":true,"
                + "\"wrong_data_rejected\":true,"
                + "\"truncated_record_rejected\":true,"
                + "\"wrong_trust_anchor_rejected\":true,"
                + "\"external_validations_completed\":1,"
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
