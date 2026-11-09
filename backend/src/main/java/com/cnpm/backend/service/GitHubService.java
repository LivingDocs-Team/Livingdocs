package com.cnpm.backend.service;

import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.stereotype.Service;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestTemplate;

import com.cnpm.backend.dto.RepositoryDto;
import com.cnpm.backend.exception.GitHubAuthenticationException;

import java.util.Arrays;
import java.util.List;

@Service
public class GitHubService {

    private final RestTemplate restTemplate;

    public GitHubService(RestTemplateBuilder restTemplateBuilder) {
        this.restTemplate = restTemplateBuilder.build();
    }

    public List<RepositoryDto> getUserRepositories(String token) {
        try {
            RepositoryDto[] repos = restTemplate.getForObject("https://api.github.com/user/repos", RepositoryDto[].class);
            return repos != null ? Arrays.asList(repos) : List.of();
        } catch (HttpClientErrorException.Unauthorized e) {
            throw new GitHubAuthenticationException("Token GitHub không hợp lệ");
        }
    }
}