#include "pp_infer/ouster_adapter.hpp"
#include <algorithm>
#include <array>
#include <cstring>

namespace pp_infer {
sensor_msgs::msg::PointCloud2 ouster_to_xyzi(
    const sensor_msgs::msg::PointCloud2& input, const std::string& source,
    const InputLimits& limits) {
  limits.validate();
  if (source != "signal" && source != "reflectivity")
    throw std::invalid_argument("intensity_source must be signal or reflectivity");
  const std::uint16_t endian = 1;
  if (input.is_bigendian || *reinterpret_cast<const unsigned char*>(&endian) != 1)
    throw std::invalid_argument("Ouster adapter requires little-endian data");
  const auto count = checked_product(input.width, input.height);
  const auto bytes = checked_product(input.row_step, input.height);
  const auto output_row = checked_product(input.width, 16);
  const auto output_bytes = checked_product(count, 16);
  if (count > limits.point_capacity || bytes > limits.maximum_cloud_bytes ||
      input.data.size() > limits.maximum_cloud_bytes || output_bytes > limits.maximum_cloud_bytes ||
      output_row > std::numeric_limits<std::uint32_t>::max())
    throw std::invalid_argument("Ouster cloud exceeds point or byte limits");
  if (input.row_step < checked_product(input.width, input.point_step) || input.data.size() != bytes)
    throw std::invalid_argument("Ouster cloud has inconsistent row_step/data length");

  using Field = sensor_msgs::msg::PointField;
  const std::array<std::string, 4> names{{"x", "y", "z", source}};
  std::array<const Field*, 4> fields{};
  std::array<std::size_t, 4> sizes{};
  for (std::size_t i = 0; i < names.size(); ++i) {
    for (const auto& field : input.fields) {
      if (field.name != names[i]) continue;
      if (fields[i]) throw std::invalid_argument("Duplicate Ouster field: " + names[i]);
      fields[i] = &field;
    }
    if (!fields[i] || fields[i]->count != 1)
      throw std::invalid_argument("Missing scalar Ouster field: " + names[i]);
    const auto type = fields[i]->datatype;
    if (i < 3 && type != Field::FLOAT32)
      throw std::invalid_argument("Ouster XYZ must be FLOAT32");
    if (type == Field::FLOAT32) sizes[i] = 4;
    else if (i == 3 && type == Field::UINT16) sizes[i] = 2;
    else if (i == 3 && type == Field::UINT8) sizes[i] = 1;
    else throw std::invalid_argument("Selected Ouster channel must be UINT8, UINT16 or FLOAT32");
    if (sizes[i] > input.point_step || fields[i]->offset > input.point_step - sizes[i])
      throw std::invalid_argument("Ouster field exceeds point_step: " + names[i]);
    for (std::size_t j = 0; j < i; ++j)
      if (fields[i]->offset < fields[j]->offset + sizes[j] &&
          fields[j]->offset < fields[i]->offset + sizes[i])
        throw std::invalid_argument("Ouster XYZ/selected channel fields overlap");
  }

  sensor_msgs::msg::PointCloud2 output;
  output.header = input.header;
  output.width = input.width;
  output.height = input.height;
  output.point_step = 16;
  output.row_step = static_cast<std::uint32_t>(output_row);
  output.is_bigendian = false;
  output.is_dense = input.is_dense;
  for (std::size_t i = 0; i < 4; ++i) {
    Field field;
    field.name = i == 3 ? "intensity" : names[i];
    field.offset = i * 4;
    field.datatype = Field::FLOAT32;
    field.count = 1;
    output.fields.push_back(field);
  }
  output.data.resize(output_bytes);
  if (count == 0) return output;
  for (std::size_t row = 0; row < input.height; ++row) {
    for (std::size_t col = 0; col < input.width; ++col) {
      const auto* point = input.data.data() + row * input.row_step + col * input.point_step;
      auto* destination = output.data.data() + row * output.row_step + col * 16;
      for (std::size_t i = 0; i < 3; ++i) {
        float value;
        std::memcpy(&value, point + fields[i]->offset, 4);
        if (!std::isfinite(value)) output.is_dense = false;
        std::memcpy(destination + i * 4, point + fields[i]->offset, 4);
      }
      const auto* channel = point + fields[3]->offset;
      double value;
      if (fields[3]->datatype == Field::UINT8) value = *channel;
      else if (fields[3]->datatype == Field::UINT16) {
        std::uint16_t raw;
        std::memcpy(&raw, channel, 2);
        value = raw;
      } else {
        float raw;
        std::memcpy(&raw, channel, 4);
        value = raw;
      }
      value /= limits.intensity_scale;
      if (!std::isfinite(value) || value < 0 || value > std::numeric_limits<float>::max())
        throw std::invalid_argument("Selected Ouster channel produces invalid FLOAT32 intensity");
      const float intensity = static_cast<float>(value);
      std::memcpy(destination + 12, &intensity, 4);
    }
  }
  return output;
}
}  // namespace pp_infer
