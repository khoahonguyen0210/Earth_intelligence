package com.example.backend.forecast;

import java.net.URI;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.dynamodb.DynamoDbClientBuilder;

@Configuration
@ConditionalOnProperty(name = "forecast.store", havingValue = "dynamodb")
public class DynamoDbConfig {

    @Bean(destroyMethod = "close")
    public DynamoDbClient dynamoDbClient(
            @Value("${dynamodb.endpoint}") String endpoint,
            @Value("${dynamodb.region}") String region,
            @Value("${dynamodb.access-key}") String accessKey,
            @Value("${dynamodb.secret-key}") String secretKey) {
        DynamoDbClientBuilder builder = DynamoDbClient.builder()
                .region(Region.of(region))
                .credentialsProvider(credentials(accessKey, secretKey));
        if (!endpoint.isBlank()) {
            builder.endpointOverride(URI.create(endpoint));
        }
        return builder.build();
    }

    private static AwsCredentialsProvider credentials(String accessKey, String secretKey) {
        if (accessKey.isBlank() || secretKey.isBlank()) {
            return DefaultCredentialsProvider.builder().build();
        }
        return StaticCredentialsProvider.create(AwsBasicCredentials.create(accessKey, secretKey));
    }
}
