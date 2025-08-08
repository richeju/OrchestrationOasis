.PHONY: scan

scan:
	docker run --rm -v $$PWD:/project -v $$PWD/.trivy-cache:/root/.cache/ aquasec/trivy:0.50.1 fs --exit-code 1 --severity HIGH,CRITICAL /project
