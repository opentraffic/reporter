package opentraffic.accumulator;

import java.io.IOException;

import org.apache.flink.api.common.io.DelimitedInputFormat;
import org.apache.flink.api.common.io.FilePathFilter;
import org.apache.flink.api.common.typeinfo.TypeInformation;
import org.apache.flink.api.java.typeutils.TypeExtractor;
import org.apache.flink.core.fs.Path;
import org.apache.flink.streaming.util.serialization.DeserializationSchema;
import org.apache.flink.streaming.util.serialization.SerializationSchema;

//we are killing two birds with one stone here, we take a cue from TextInputFormat (which reads line by line from input)
//so that we can convert each line of a file into a GPSMessage object but at the same time we implement (de)serialization
//so that we can convert each message from a kafka source into a GPSMessage object as well
public class GPSMessageSchema extends DelimitedInputFormat<GPSMessage> implements DeserializationSchema<GPSMessage>, SerializationSchema<GPSMessage> {

  private static final long serialVersionUID = 1L;
  private static final byte CARRIAGE_RETURN = (byte)'\r';
  private static final byte NEW_LINE = (byte)'\n';
  private static final String charsetName = "UTF-8";
  
  //using it for (de)serialization
  public GPSMessageSchema() {
    super(null, null);
    super.setCharset(charsetName);
  }
  
  //using it for line by line file parsing
  public GPSMessageSchema(String filePath) {
    super(new Path(filePath), null);
    super.setCharset(charsetName);
    super.setFilesFilter(FilePathFilter.createDefaultFilter());
  }

  @Override
  public GPSMessage readRecord(GPSMessage reuse, byte[] bytes, int offset, int numBytes) throws IOException {
    //Check if \n is used as delimiter and the end of this line is a \r, then remove \r from the line
    if (this.getDelimiter() != null && this.getDelimiter().length == 1 
      && this.getDelimiter()[0] == NEW_LINE && offset+numBytes >= 1 
      && bytes[offset+numBytes-1] == CARRIAGE_RETURN){
      numBytes -= 1;
    }
    return GPSMessage.fromString(new String(bytes, offset, numBytes, charsetName));
  }

// --------------------------------------------------------------------------------------------

  @Override
  public String toString() {
      return "GPSMessageSchema (" + getFilePath() + ") - " + charsetName;
  }

  @Override
  public GPSMessage deserialize(byte[] message) throws IOException {
    return GPSMessage.fromString(new String(message));
  }

  @Override
  public boolean isEndOfStream(GPSMessage nextElement) {
    return false;
  }

  @Override
  public byte[] serialize(GPSMessage element) {
    return element.toString().getBytes();
  }

  @Override
  public TypeInformation<GPSMessage> getProducedType() {
    return TypeExtractor.getForClass(GPSMessage.class);
  }
}