# F1 Race Predictions

A machine learning project that predicts Formula 1 race outcomes using historical racing data, qualifying times, and sector performance analysis.

## Overview

This project leverages advanced machine learning techniques to forecast F1 race results by analyzing qualifying performance, sector times, and historical race data. Built with Python and scikit-learn, it demonstrates practical applications of predictive modeling in sports analytics.

## Features

- **Data Collection**: Automated retrieval of F1 race data using the FastF1 API
- **Feature Engineering**: Analysis of qualifying times, sector performance, and lap times
- **Predictive Modeling**: Gradient Boosting Regressor for race time predictions
- **Multi-Season Analysis**: Comparative analysis across 2023, 2024, and 2025 seasons
- **Performance Evaluation**: Model validation with Mean Absolute Error metrics

## Tech Stack

- **Python 3.12**
- **Machine Learning**: scikit-learn, XGBoost
- **Data Processing**: pandas, numpy
- **Visualization**: matplotlib, seaborn
- **F1 Data**: FastF1 API
- **Environment**: Jupyter Notebook

## Key Components

### Abu Dhabi Grand Prix Prediction
- Analyzes qualifying results from multiple seasons
- Incorporates sector time analysis for enhanced accuracy
- Predicts race finishing times based on qualifying performance
- Handles missing data gracefully with fallback mechanisms

## Model Architecture

The prediction pipeline follows these steps:

1. **Data Acquisition**: Fetch qualifying and race data from FastF1
2. **Feature Extraction**: Calculate average sector times and lap times per driver
3. **Data Merging**: Combine qualifying times with historical performance metrics
4. **Training**: Gradient Boosting Regressor with cross-validation
5. **Prediction**: Generate race time forecasts for upcoming events

## Results

The model achieves competitive accuracy in predicting race outcomes, with performance metrics displayed for each prediction run. The system successfully handles driver lineup changes and adapts to new circuit configurations.

## Future Enhancements

- Weather data integration for improved accuracy
- Tire strategy analysis
- Real-time predictions during race weekends
- Extended support for all F1 circuits
- Deep learning model comparison

## Usage

```python
# Install dependencies
pip install -r requirements.txt

# Run the prediction notebook
jupyter notebook abu_dhabi_race_prediction_fixed.ipynb
```

## Data Source

Race data provided by the [FastF1 Python library](https://github.com/theOehrly/Fast-F1), which accesses the official F1 live timing data.

## License

This project is for educational and portfolio purposes.

---

**Note**: Predictions are based on historical data and should not be used for betting or gambling purposes.
