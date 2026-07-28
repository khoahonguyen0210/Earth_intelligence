package com.example.backend.storage;

import java.net.URI;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

/**
 * Points the AWS S3 SDK at the local MinIO container (infra/docker), not
 * real AWS -- MinIO is S3-API-compatible, so the same S3Client code will
 * work unchanged against real AWS S3 in the later infra phase
 * (PROJECT_BIBLE.md's final definition of done).
 */
@Configuration
public class S3ClientConfig {

    @Bean
    public S3Client s3Client(
            @Value("${object-store.endpoint}") String endpoint,
            @Value("${object-store.access-key}") String accessKey,
            @Value("${object-store.secret-key}") String secretKey) {
        return S3Client.builder()
                .endpointOverride(URI.create(endpoint))
                .region(Region.US_EAST_1)
                .credentialsProvider(StaticCredentialsProvider.create(AwsBasicCredentials.create(accessKey, secretKey)))
                .serviceConfiguration(S3Configuration.builder().pathStyleAccessEnabled(true).build())
                .build();
    }
}
