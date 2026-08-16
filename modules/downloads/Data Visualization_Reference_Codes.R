# EPPS Math & Coding Camp — Module 5: Data Visualization
# Reference script 


# Reference lines with abline() (page 9)
mean_le <- mean(life_exp$Average_Life_Expectancy, na.rm = TRUE)
median_le <- median(life_exp$Average_Life_Expectancy, na.rm = TRUE)

hist(life_exp$Average_Life_Expectancy,
     main = "Life Expectancy with Mean and Median",
     xlab = "Average Life Expectancy",
     col = "lightblue", border = "black")
abline(v = mean_le, col = "blue", lwd = 2)
abline(v = median_le, col = "red", lwd = 2)
legend("topleft", legend = c("Mean", "Median"), col = c("blue", "red"), lwd = 2)


# range() covers the full dataset, not just one subset (page 32)
# Continues from the male_data/female_data subsets and single-line
# plot already typed by hand earlier.
male_data <- subset(life_exp, Gender == "Male")
female_data <- subset(life_exp, Gender == "Female")

plot(male_data$Year, male_data$Average_Life_Expectancy,
     type = "l", col = "blue", lwd = 2,
     xlab = "Year", ylab = "Average Life Expectancy",
     xlim = range(life_exp$Year),
     ylim = range(life_exp$Average_Life_Expectancy, na.rm = TRUE))
lines(female_data$Year, female_data$Average_Life_Expectancy, col = "red", lwd = 2)

legend("bottomright", legend = c("Male", "Female"), col = c("blue", "red"), lwd = 2)


# One mapping, two layers colored (page 47)
library(ggplot2)

ggplot(data = ev, aes(x = Model_Year, y = Electric_Range, color = Electric_Vehicle_Type)) +
  geom_point(alpha = .5, size = 2) +
  geom_smooth(method = "lm", se = FALSE, linewidth = 1.5)


# One column, two panels, four labels (page 50)
ev$range_group <- ifelse(ev$Electric_Range >= 200, "long range", "short range")

ggplot(data = ev, aes(x = Model_Year, y = Electric_Range, color = Electric_Vehicle_Type)) +
  geom_point(alpha = .5) +
  geom_smooth(method = "lm", se = FALSE) +
  facet_wrap(~range_group) +
  labs(title = "Electric range by model year",
       subtitle = "By vehicle type and range category",
       x = "Model Year", y = "Electric Range (miles)", color = "Vehicle Type")


# One layer, a different look (page 53)
ev$range_group <- ifelse(ev$Electric_Range >= 200, "long range", "short range")

ggplot(data = ev, aes(x = Model_Year, y = Electric_Range, color = Electric_Vehicle_Type)) +
  geom_point(alpha = .5) +
  geom_smooth(method = "lm", se = FALSE) +
  facet_wrap(~range_group) +
  labs(title = "Electric range by model year",
       subtitle = "By vehicle type and range category",
       x = "Model Year", y = "Electric Range (miles)", color = "Vehicle Type") +
  theme_minimal()
