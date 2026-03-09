[readme.md](https://github.com/user-attachments/files/25833980/readme.md)
# FeRAM Analyzer: Automated PUND & Endurance Analysis Tool

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-App-red)](https://streamlit.io/)
[![Status](https://img.shields.io/badge/Status-Active-success)]()

## Overview
This project is a specialized Python-based tool designed for **Ferroelectric Random Access Memory (FeRAM)** characterization. It automates the processing of raw measurement data (from Keysight B1500A/Keithley 4200), utilizing the **PUND algorithm** to extract accurate ferroelectric properties while compensating for leakage currents and signal drift.

## Key Features

### 1. Advanced Physics Algorithms
* **PUND Correction**: Automatically identifies $P, U, N, D$ pulses with adaptive thresholding to remove non-ferroelectric components.
* **Leakage Compensation**: Implements linear compensation to fix "spiraling" hysteresis loops caused by resistive leakage.
* **Cycle Isolation**: Smartly detects and isolates single-period waveforms from continuous measurement streams.

### 2.Interactive Visualization
* **P-E Hysteresis Loops**: Overlay multiple cycles (e.g., $10^0$ to $10^9$) with customizable color maps (Viridis, Plasma, etc.).
* **Endurance Trends**: Automatically extracts and plots **$2P_r$** (Remnant Polarization) and **$2V_c$** (Coercive Voltage) over logarithmic cycle scales.
* **Data Table**: Instant view of key metrics for selected cycles.

### 3. AI Integration
* **Gemini Assistant**: Built-in integration with Google Gemini AI to analyze fatigue, wake-up effects, and potential breakdown mechanisms based on the extracted data.

## Installation & Usage
 

### Run Locally
1. Clone the repository:
   ```bash
   pip install -r requirements.txt
