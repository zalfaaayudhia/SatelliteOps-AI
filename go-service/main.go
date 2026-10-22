package main

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"time"
)

type AnalyzeRequest struct {
	Message string `json:"message"`
}

type AnalyzeResponse struct {
	Status          string `json:"status"`
	Service         string `json:"service"`
	ReceivedMessage string `json:"received_message"`
	Analysis        string `json:"analysis"`
}

func main() {
	mux := http.NewServeMux()

	client := &http.Client{
		Timeout: 10 * time.Second,
	}

	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{
			"status":  "ok",
			"service": "go-api",
		})
	})

	mux.HandleFunc("POST /analyze", func(w http.ResponseWriter, r *http.Request) {
		var request AnalyzeRequest

		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			http.Error(w, `{"error":"invalid JSON request"}`, http.StatusBadRequest)
			return
		}

		if request.Message == "" {
			http.Error(w, `{"error":"message is required"}`, http.StatusBadRequest)
			return
		}

		payload, err := json.Marshal(request)
		if err != nil {
			http.Error(w, `{"error":"failed to encode request"}`, http.StatusInternalServerError)
			return
		}

		pythonURL := "http://localhost:8000/analyze"
		pythonRequest, err := http.NewRequestWithContext(
			r.Context(),
			http.MethodPost,
			pythonURL,
			bytes.NewReader(payload),
		)
		if err != nil {
			http.Error(w, `{"error":"failed to create Python request"}`, http.StatusInternalServerError)
			return
		}

		pythonRequest.Header.Set("Content-Type", "application/json")

		response, err := client.Do(pythonRequest)
		if err != nil {
			http.Error(w, `{"error":"Python AI service unavailable"}`, http.StatusBadGateway)
			return
		}
		defer response.Body.Close()

		body, err := io.ReadAll(response.Body)
		if err != nil {
			http.Error(w, `{"error":"failed to read Python response"}`, http.StatusBadGateway)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(response.StatusCode)
		_, _ = w.Write(body)
	})

	log.Println("SatelliteOps AI Go API running on :8080")

	if err := http.ListenAndServe(":8080", mux); err != nil {
		log.Fatal(err)
	}
}
