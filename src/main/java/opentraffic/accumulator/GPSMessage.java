package opentraffic.accumulator;

import java.io.IOException;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

import org.joda.time.DateTime;
import org.joda.time.format.DateTimeFormat;
import org.joda.time.format.DateTimeFormatter;

public class GPSMessage {
  private static final transient DateTimeFormatter timeFormatter =
    DateTimeFormat.forPattern("yyyy-MM-dd HH:mm:ss").withLocale(Locale.US).withZoneUTC();
  private static final transient DecimalFormat floatFormatter = new DecimalFormat("###.######", new DecimalFormatSymbols(Locale.US));
  public static final int appxWireSize = 128; //approximate number of chars that a single one of these takes up in json
  
  public String uuid;
  public float lat;
  public float lon;
  public long epoch;
  public int accuracy;
  public String trace;
  
  public GPSMessage(String uuid, float lat, float lon, long epoch_milli, int accuracy) {
    this.uuid = uuid;
    this.lat = lat;
    this.lon = lon;
    this.epoch = epoch_milli;
    this.accuracy = accuracy;

    //convert this info to the format we are going to use over the wire
    StringBuilder sb = new StringBuilder();
    sb.ensureCapacity(appxWireSize);
    sb.append("{\"lat\":");
    sb.append(floatFormatter.format(lat)).append(",\"lon\":");
    sb.append(floatFormatter.format(lon)).append(",\"time\":");
    sb.append(Long.toString(epoch/1000l)).append(",\"accuracy\":");
    sb.append(Integer.toString(accuracy)).append("}");
    trace = sb.toString();
  }

  public String toString() {
    StringBuilder sb = new StringBuilder();
    sb.append(uuid).append('|');
    sb.append(floatFormatter.format(lat)).append('|');
    sb.append(floatFormatter.format(lon)).append('|');
    sb.append((new DateTime(epoch)).toString(timeFormatter)).append('|');
    sb.append(Integer.toString(accuracy));
    return sb.toString();
  }
  
  public static GPSMessage fromString(String line) throws IOException {
    try {
      String[] tokens = line.split("\\|");
      float lat = floatFormatter.parse(tokens[9]).floatValue();
      float lon = floatFormatter.parse(tokens[10]).floatValue();
      long epoch = DateTime.parse(tokens[0], timeFormatter).getMillis();
      int accuracy = (int)Math.ceil(floatFormatter.parse(tokens[5]).floatValue());  
      return new GPSMessage(tokens[1], lat, lon, epoch, accuracy);
    }
    catch (Exception e) {
      throw new IOException("Invalid record: " + line, e);
    }
  }

  @Override
  public int hashCode() {
    final int prime = 31;
    int result = 1;
    result = prime * result + accuracy;
    result = prime * result + (int) (epoch ^ (epoch >>> 32));
    result = prime * result + Float.floatToIntBits(lat);
    result = prime * result + Float.floatToIntBits(lon);
    result = prime * result + ((uuid == null) ? 0 : uuid.hashCode());
    return result;
  }

  @Override
  public boolean equals(Object obj) {
    if (this == obj)
      return true;
    if (obj == null)
      return false;
    if (getClass() != obj.getClass())
      return false;
    GPSMessage other = (GPSMessage) obj;
    if (accuracy != other.accuracy)
      return false;
    if (epoch != other.epoch)
      return false;
    if (Float.floatToIntBits(lat) != Float.floatToIntBits(other.lat))
      return false;
    if (Float.floatToIntBits(lon) != Float.floatToIntBits(other.lon))
      return false;
    if (uuid == null) {
      if (other.uuid != null)
        return false;
    } else if (!uuid.equals(other.uuid))
      return false;
    return true;
  }
}
